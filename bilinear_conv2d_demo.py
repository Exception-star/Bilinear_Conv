# -*- encoding: utf-8 -*-
# Software: PyCharm
# Time    : 2019/11/25 
# Author  : Wang
# File    : bilinear_conv2d.py

import torch
import torch.nn as nn
import torch.nn.functional as F


def repeat(x, n):
    temp = [x]
    for i in range(n-1):
        temp.append(x)
    return temp


def _ntuple(n):
    def parse(x):
        if isinstance(x, tuple):
            return x
        return tuple(repeat(x, n))
    return parse


_single = _ntuple(1)
_pair = _ntuple(2)
_triple = _ntuple(3)
_quadruple = _ntuple(4)


def change_kernel_size(kernel_size, dilation):
    if isinstance(kernel_size, tuple):
        assert len(kernel_size) == len(dilation), "kernel_size length should be equal dilation length"
        kernel_size_new = tuple([(dilation[0] - 1) * (kernel_size[0] - 1) + kernel_size[0],
                                (dilation[1] - 1) * (kernel_size[1] - 1) + kernel_size[1]])
    elif isinstance(kernel_size, int):
        kernel_size_new = (dilation - 1) * (kernel_size - 1) + kernel_size
    else:
        raise ValueError('unknow')
    return kernel_size_new


class BilinearConv2d(nn.Conv2d):
    r"""Applies a 2D convolution over an input signal composed of several input
        planes.

        In the simplest case, the output value of the layer with input size
        :math:`(N, C_{\text{in}}, H, W)` and output :math:`(N, C_{\text{out}}, H_{\text{out}}, W_{\text{out}})`
        can be precisely described as:

        .. math::
            \text{out}(N_i, C_{\text{out}_j}) = \text{bias}(C_{\text{out}_j}) +
            \sum_{k = 0}^{C_{\text{in}} - 1} \text{weight}(C_{\text{out}_j}, k) \star \text{input}(N_i, k)


        where :math:`\star` is the valid 2D `cross-correlation`_ operator,
        :math:`N` is a batch size, :math:`C` denotes a number of channels,
        :math:`H` is a height of input planes in pixels, and :math:`W` is
        width in pixels.

        * :attr:`stride` controls the stride for the cross-correlation, a single
          number or a tuple.

        * :attr:`padding` controls the amount of implicit zero-paddings on both
          sides for :attr:`padding` number of points for each dimension.

        * :attr:`dilation` controls the spacing between the kernel points; also
          known as the à trous algorithm. It is harder to describe, but this `link`_
          has a nice visualization of what :attr:`dilation` does.

        * :attr:`groups` controls the connections between inputs and outputs.
          :attr:`in_channels` and :attr:`out_channels` must both be divisible by
          :attr:`groups`. For example,

            * At groups=1, all inputs are convolved to all outputs.
            * At groups=2, the operation becomes equivalent to having two conv
              layers side by side, each seeing half the input channels,
              and producing half the output channels, and both subsequently
              concatenated.
            * At groups= :attr:`in_channels`, each input channel is convolved with
              its own set of filters, of size:
              :math:`\left\lfloor\frac{out\_channels}{in\_channels}\right\rfloor`.

        The parameters :attr:`kernel_size`, :attr:`stride`, :attr:`padding`, :attr:`dilation` can either be:

            - a single ``int`` -- in which case the same value is used for the height and width dimension
            - a ``tuple`` of two ints -- in which case, the first `int` is used for the height dimension,
              and the second `int` for the width dimension

        .. note::

             Depending of the size of your kernel, several (of the last)
             columns of the input might be lost, because it is a valid `cross-correlation`_,
             and not a full `cross-correlation`_.
             It is up to the user to add proper padding.

        .. note::

            When `groups == in_channels` and `out_channels == K * in_channels`,
            where `K` is a positive integer, this operation is also termed in
            literature as depthwise convolution.

            In other words, for an input of size :math:`(N, C_{in}, H_{in}, W_{in})`,
            a depthwise convolution with a depthwise multiplier `K`, can be constructed by arguments
            :math:`(in\_channels=C_{in}, out\_channels=C_{in} \times K, ..., groups=C_{in})`.

        .. include:: cudnn_deterministic.rst

        Args:
            in_channels (int): Number of channels in the input image
            out_channels (int): Number of channels produced by the convolution
            kernel_size (int or tuple): Size of the convolving kernel
            stride (int or tuple, optional): Stride of the convolution. Default: 1
            padding (int or tuple, optional): Zero-padding added to both sides of the input. Default: 0
            padding_mode (string, optional). Accepted values `zeros` and `circular` Default: `zeros`
            dilation (int or tuple, optional): Spacing between kernel elements. Default: 1
            groups (int, optional): Number of blocked connections from input channels to output channels. Default: 1
            bias (bool, optional): If ``True``, adds a learnable bias to the output. Default: ``True``

        Shape:
            - Input: :math:`(N, C_{in}, H_{in}, W_{in})`
            - Output: :math:`(N, C_{out}, H_{out}, W_{out})` where

              .. math::
                  H_{out} = \left\lfloor\frac{H_{in}  + 2 \times \text{padding}[0] - \text{dilation}[0]
                            \times (\text{kernel\_size}[0] - 1) - 1}{\text{stride}[0]} + 1\right\rfloor

              .. math::
                  W_{out} = \left\lfloor\frac{W_{in}  + 2 \times \text{padding}[1] - \text{dilation}[1]
                            \times (\text{kernel\_size}[1] - 1) - 1}{\text{stride}[1]} + 1\right\rfloor

        Attributes:
            weight (Tensor): the learnable weights of the module of shape
                             :math:`(\text{out\_channels}, \frac{\text{in\_channels}}{\text{groups}},`
                             :math:`\text{kernel\_size[0]}, \text{kernel\_size[1]})`.
                             The values of these weights are sampled from
                             :math:`\mathcal{U}(-\sqrt{k}, \sqrt{k})` where
                             :math:`k = \frac{1}{C_\text{in} * \prod_{i=0}^{1}\text{kernel\_size}[i]}`
            bias (Tensor):   the learnable bias of the module of shape (out_channels). If :attr:`bias` is ``True``,
                             then the values of these weights are
                             sampled from :math:`\mathcal{U}(-\sqrt{k}, \sqrt{k})` where
                             :math:`k = \frac{1}{C_\text{in} * \prod_{i=0}^{1}\text{kernel\_size}[i]}`

        Examples::

            >>> # With square kernels and equal stride
            >>> m = nn.BilinearConv2d(16, 33, 3, stride=2)
            >>> # non-square kernels and unequal stride and with padding
            >>> m = nn.BilinearConv2d(16, 33, (3, 5), stride=(2, 1), padding=(4, 2))
            >>> # non-square kernels and unequal stride and with padding and dilation
            >>> m = nn.BilinearConv2d(16, 33, (3, 5), stride=(2, 1), padding=(4, 2), dilation=(3, 1))
            >>> input = torch.randn(20, 16, 50, 100)
            >>> output = m(input)

        .. _cross-correlation:
            https://en.wikipedia.org/wiki/Cross-correlation

        .. _link:
            https://github.com/vdumoulin/conv_arithmetic/blob/master/README.md
        """
    __constants__ = ['stride', 'padding', 'dilation', 'groups', 'bias', 'padding_mode']

    def __init__(self, in_channels, out_channels, kernel_size, stride=1,
                 padding=0, dilation=1, groups=1,
                 bias=True, padding_mode='zeros'):
        kernel_size = _pair(kernel_size)
        stride = _pair(stride)
        padding = _pair(padding)
        dilation = _pair(dilation)
        self.bilinear = True if dilation[0] > 1 or dilation[1] > 1 else False
        self.kernel_size_new = change_kernel_size(kernel_size, dilation)
        super(BilinearConv2d, self).__init__(
            in_channels, out_channels, kernel_size, stride=stride,
            padding=padding, dilation=dilation, groups=groups,
            bias=bias, padding_mode=padding_mode)

    def forward(self, input):
        expand_weight = F.interpolate(self.weight,
                                      size=self.kernel_size_new,
                                      mode='bilinear',
                                      align_corners=True)
        if self.padding_mode == 'circular':
            expanded_padding = ((self.padding[1] + 1) // 2, self.padding[1] // 2,
                                (self.padding[0] + 1) // 2, self.padding[0] // 2)
            return F.conv2d(F.pad(input, expanded_padding, mode='circular'),
                            expand_weight, self.bias, self.stride,
                            0, 1, self.groups)
        return F.conv2d(input, expand_weight, self.bias, self.stride,
                        self.padding, 1, self.groups)


if __name__ == '__main__':
    torch.manual_seed(1)
    input = torch.randn(20, 16, 50, 100)
    # With square kernels and equal stride
    m = BilinearConv2d(16, 33, 3, stride=2)
    output = m(input)
    print(m.dilation)
    print(output.shape)
    # non-square kernels and unequal stride and with padding
    m = BilinearConv2d(16, 33, (3, 5), stride=(2, 1), padding=(4, 2))
    output = m(input)
    print(m.dilation)
    print(output.shape)
    # non-square kernels and unequal stride and with padding and dilation
    m = BilinearConv2d(16, 33, kernel_size=(3, 5), stride=(2, 1), padding=(4, 2), dilation=(3, 1))
    output = m(input)
    print(m.dilation)
    print(output.shape)
    m = BilinearConv2d(16, 16, kernel_size=(3, 3), stride=(2, 1), padding=(4, 16), dilation=(4, 16), groups=8)

    output = m(input)
    print(m.dilation)
    print(output.shape)
