from maeri.compiler.assembler.states import ConfigForward, ConfigUp
from maeri.compiler.assembler.states import InjectEn

from enum import IntEnum, unique

bytes_in_address = None
num_nodes = None
num_adders = None
num_mults = None
num_ports = None
INPUT_WIDTH = None

class InitISA():
    def __init__(self, _bytes_in_address, _num_nodes, 
            _num_adders, _num_mults, _input_width, _num_ports):
        global bytes_in_address
        bytes_in_address = _bytes_in_address

        global num_nodes
        num_nodes = _num_nodes

        global num_adders
        num_adders = _num_adders

        global num_mults
        num_mults = _num_mults

        global num_ports
        num_ports = _num_ports

        global INPUT_WIDTH
        INPUT_WIDTH = _input_width


@unique
class Opcodes(IntEnum):
    undefined = 0
    reset = 1
    configure_states = 2
    configure_weights = 3
    configure_collectors = 4
    configure_relus = 5
    load_features = 6
    store_features = 7
    run = 8
    debug = 9

class Reset():
    op = Opcodes.reset

class ConfigureStates():
    op = Opcodes.configure_states

    def __init__(self, states):
        assert(len(states) == num_nodes)
        self.states = states

        for state in states[:num_adders]:
            assert(any([state in ConfigForward, state in ConfigUp]))

        for state in states[num_adders:]:
            assert(state in InjectEn)

    @staticmethod
    def num_params():
        return bytes_in_address

class ConfigureWeights():
    op = Opcodes.configure_weights

    def __init__(self, weights):
        assert(len(weights) == num_mults)
        min = (-1)*(2**(INPUT_WIDTH - 1))
        max = 2**(INPUT_WIDTH - 1) -1

        for weight in weights:
            assert(min <= weight <= max)

        self.weights = weights

    @staticmethod
    def num_params():
        return bytes_in_address

class ConfigureCollectors():
    op = Opcodes.configure_collectors

    def __init__(self, node_ids):
        assert(len(node_ids) == num_nodes)
        min = 0
        max = 255

        for node_id in node_ids:
            assert(min <= node_id <= max)

        self.node_ids = node_ids

    @staticmethod
    def num_params():
        return bytes_in_address

class LoadFeatures():
    op = Opcodes.load_features

    def __init__(self, port_buffer_address, num_lines, address):
        self.port_buffer_address = port_buffer_address
        self.num_lines = num_lines
        self.address = address

    @staticmethod
    def num_params():
        return bytes_in_address + 3

class StoreFeatures():
    op = Opcodes.store_features

    def __init__(self, port_buffer_address, num_lines, address):
        self.port_buffer_address = port_buffer_address
        self.num_lines = num_lines
        self.address = address

    @staticmethod
    def num_params():
        return bytes_in_address + 3

class Run():
    op = Opcodes.run

    def __init__(self, len_runtime, pace):
        self.len_runtime = len_runtime
        self.pace = pace

    @staticmethod
    def num_params():
        return 2

class Debug():
    op = Opcodes.debug

    def __init__(self):
        pass

    @staticmethod
    def num_params():
        return 0