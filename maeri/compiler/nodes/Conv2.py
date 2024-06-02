from maeri.common.logger import LogIndent, logger
from scipy.signal import correlate2d
from .Output import Output
from .Input import Input
import numpy as np

class Conv2():
    def __init__(self, X, W, res, pad):
        self.X = X
        self.W = W
        self.res = res

        self.pad_left = pad[0]
        self.pad_upper = pad[1]
        self.pad_right = pad[2]
        self.pad_bottom = pad[3]
    
    def split_to_ports(self, no_ports):
        op_graph = []
        input_depth = (self.X.slice[2].stop - self.X.slice[2].start)

        # probably already checked this actually...
        # but again, only allowing square filters and
        # by extension, square padding
        assert(self.pad_upper == self.pad_bottom)

        # check that effective filter fits within the 
        # number of ports, where the effective filter considers
        # padding
        filter_depth = self.W.mem_ref.data.shape[2]
        effective_depth = filter_depth + self.pad_bottom + self.pad_upper
        assert(effective_depth <= no_ports)

        # we must split the operator input field depthwise
        # into new inputs

        # we first handle padding above the input field
        offset = filter_depth - self.pad_upper
        for padding in range(self.pad_upper):
            input_slice = slice(0, padding + offset)
            input_slice = (self.X.slice[0], self.X.slice[1], input_slice, self.X.slice[3])
            X_input = Input(input_slice, self.X.mem_ref)

            output_slice = (self.res.slice[0], self.res.slice[1], padding, self.res.slice[3])
            res = Output(output_slice, self.res.mem_ref)

            pad = [self.pad_left, self.pad_upper - padding, self.pad_right, 0]

            op_graph += [Conv2(X_input, self.W, res, pad)]

        # now we handle the input field
        out_inner_len = input_depth - filter_depth + 1

        for index in range(out_inner_len):
            input_slice = slice(index, index + filter_depth)
            input_slice = (self.X.slice[0], self.X.slice[1], input_slice, self.X.slice[3])
            X_input = Input(input_slice, self.X.mem_ref)

            output_slice = (self.res.slice[0], self.res.slice[1], index + self.pad_upper, self.res.slice[3])
            res = Output(output_slice, self.res.mem_ref)

            pad = [self.pad_left, 0, self.pad_right, 0]

            op_graph += [Conv2(X_input, self.W, res, pad)]

        # last, we handle padding below the input field
        for padding in range(self.pad_bottom):
            if padding == (filter_depth - 1):
                input_slice = input_depth - 1
            else:
                input_slice = slice(out_inner_len + padding, input_depth)

            input_slice = (self.X.slice[0], self.X.slice[1], input_slice, self.X.slice[3])
            X_input = Input(input_slice, self.X.mem_ref)

            output_slice = (self.res.slice[0], self.res.slice[1], out_inner_len + self.pad_upper + padding, self.res.slice[3])
            res = Output(output_slice, self.res.mem_ref)

            pad = [self.pad_left, 0, self.pad_right, padding + 1]

            op_graph += [Conv2(X_input, self.W, res, pad)]
        
        return op_graph
    
    def split_left_right(self):
        op_graph = []
        filter_width = self.W.mem_ref.data.shape[2]
        input_shape = self.X.slice[3].stop - self.X.slice[3].start
        inner_output_len = input_shape - filter_width + 1
        
        left_len = inner_output_len//2
        right_len = inner_output_len - left_len

        # slices
        X_slice = self.X.slice
        W_slice = self.W.slice
        res_slice = self.res.slice

        # results as outputs
        offset = res_slice[3].start
        left_output_slice = slice(offset, offset + self.pad_left + left_len)
        left_output_slice = (res_slice[0], res_slice[1], res_slice[2], left_output_slice)
        left_res = Output(left_output_slice, self.res.mem_ref)

        right_output_slice = slice(offset + self.pad_left + left_len, res_slice[3].stop)
        right_output_slice = (res_slice[0], res_slice[1], res_slice[2], right_output_slice)
        right_res = Output(right_output_slice, self.res.mem_ref)

        diff = res_slice[3].stop - res_slice[3].start
        assert(diff == (self.pad_left + left_len + right_len + self.pad_right))

        # form new inputs
        begin = X_slice[3].start
        X_slice_left = left_len + filter_width - 1
        X_slice_left = slice(begin, begin + X_slice_left)
        X_slice_left = (X_slice[0], X_slice[1], X_slice[2], X_slice_left)
        logger.debug(f"X_slice_left = {X_slice_left}")
        X_input_left = Input(X_slice_left, self.X.mem_ref)

        end = X_slice[3].stop
        X_slice_right = slice((end - filter_width) - (right_len - 1), end)
        X_slice_right = (X_slice[0], X_slice[1], X_slice[2], X_slice_right)
        logger.debug(f"X_slice_right = {X_slice_right}")
        X_input_right = Input(X_slice_right, self.X.mem_ref)

        # schedule convolution operators
        pad_left = [self.pad_left, self.pad_upper, 0, self.pad_bottom]
        op_graph += [Conv2(X_input_left, self.W, left_res, pad_left)]
        pad_right = [0, self.pad_upper, self.pad_right, self.pad_bottom]
        op_graph += [Conv2(X_input_right, self.W, right_res, pad_right)]


        # verify resulting computation is possible
        input_width = (X_slice_left[3].stop - X_slice_left[3].start) + pad_left[0]
        logger.debug(f"filter_width = {filter_width}")
        logger.debug(f"input_width = {input_width}")
        if input_width < filter_width:
            message = f"input_width : {input_width} is less than " + \
                f"filter_width : {filter_width}"
            raise RuntimeError(message)

        input_width = (X_slice_right[3].stop - X_slice_right[3].start) + pad_right[2]
        if input_width < filter_width:
            message = f"input_width : {input_width} is less than " + \
                f"filter_width : {filter_width}"
            raise RuntimeError(message)

        return op_graph
    
    def sim(self):
        logger.debug("EXECUTING CONV")

        # get input
        X = self.X.get_data()

        # pad input
        x_shape = list(X.shape)
        x_shape[0] += self.pad_upper + self.pad_bottom
        x_shape[1] += self.pad_left + self.pad_right
        X_padded = np.zeros(x_shape)

        # form slice where data will be placed in x_padded
        slice_h = slice(self.pad_upper, x_shape[0] - self.pad_bottom)
        slice_w = slice(self.pad_left, x_shape[1] - self.pad_right)
        X_padded[slice_h, slice_w] = X
        logger.debug(f"X = \n{X_padded}")

        # get filter
        W = self.W.get_data()
        logger.debug(f"W = \n{W}")

        # compute result
        res = correlate2d(X_padded, W, mode='valid')
        self.res.write_data(res)

        logger.debug(f"res = \n{self.res.debug()}")
    
    def debug(self):
        X_raw = self.X.get_data()
        W_raw = self.W.get_data()
        res_raw = self.res.debug()

        logger.debug(f"X_slice = {self.X.slice}")
        logger.debug(f"X_raw = {X_raw}")
        logger.debug(f"W_raw = {W_raw}")
        logger.debug(f"res_raw = {res_raw}")

        logger.debug(f"self.pad_left  = {self.pad_left}")
        logger.debug(f"self.pad_upper  = {self.pad_upper}")
        logger.debug(f"self.pad_right  = {self.pad_right}")
        logger.debug(f"self.pad_bottom  = {self.pad_bottom}")
