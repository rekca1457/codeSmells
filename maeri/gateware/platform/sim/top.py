from nmigen import  Signal, Module, DomainRenamer
from nmigen import Record, Elaboratable

from luna.gateware.stream import StreamInterface

from maeri.gateware.platform.sim.mem import Mem
from maeri.gateware.platform.shared.store import Store
from maeri.gateware.platform.shared.load import Load
from maeri.gateware.platform.shared.serial_link import SerialLink
from maeri.gateware.platform.shared.interface_controller import InterfaceController
from maeri.gateware.platform.shared.load_afifo import LoadAfifo
from maeri.gateware.platform.shared.store_afifo import StoreAfifo
from maeri.gateware.compute_unit.top import Top as ComputeUnit
from nmigen.lib.fifo import AsyncFIFOBuffered

from maeri.common.domains import comm_domain, comm_period
from maeri.common.domains import compute_domain, compute_period

class Top(Elaboratable):
    def __init__(self, max_packet_size=32, mem_depth=256, init=None):
        mem_width = 32
        # config
        config = {}
        config['b_in_packet'] = max_packet_size
        config['b_in_line'] = mem_width//8
        config['m_depth'] = mem_depth

        if ((mem_depth*(mem_width//8)) % max_packet_size):
            raise ValueError("MEM_SIZE MUST BE A MULTIPLE OF MAX_PACKET_SIZE")

        # instantiate submodules
        self.mem = mem = Mem(width=mem_width, depth=mem_depth, init=init)
        self.serial_link = SerialLink(sim=True, max_packet_size=max_packet_size)
        self.load_unit = \
            Load(mem.addr_shape, mem.data_shape, max_packet_size)
        self.store_unit = \
            Store(mem.addr_shape, mem.data_shape, max_packet_size)
        self.interface_controller = \
            InterfaceController(mem.addr_shape, mem.data_shape, 
            max_packet_size, mem_depth, config)
        self.load_afifo = \
            LoadAfifo(mem.addr_shape, mem.data_shape, max_packet_size=max_packet_size,
            comm_domain=comm_domain, compute_domain=compute_domain)
        self.store_afifo = \
            StoreAfifo(mem.addr_shape, mem.data_shape, max_packet_size=max_packet_size,
            comm_domain=comm_domain, compute_domain=compute_domain)
        self.compute_unit = ComputeUnit(
                                addr_shape = 24,
                                data_shape = 32,
                                depth = 6,
                                num_ports = 16,
                                INPUT_WIDTH = 8, 
                                bytes_in_line = 4,
                                VERBOSE=False
                                )
        config['ports'] = self.compute_unit.num_ports
        config['no.mults'] = self.compute_unit.num_mults

        # parameters
        self.max_packet_size = max_packet_size
    
    def elaborate(self, platform):
        m = Module()

        # attach submodules
        m.submodules.serial_link = serial_link = self.serial_link
        m.submodules.mem = mem = DomainRenamer(compute_domain)(self.mem)
        m.submodules.load_unit = load_unit = \
            DomainRenamer(comm_domain)(self.load_unit)
        m.submodules.store_unit = store_unit = \
            DomainRenamer(comm_domain)(self.store_unit)
        m.submodules.interface_controller = interface_controller = \
            DomainRenamer(comm_domain)(self.interface_controller)
        m.submodules.load_afifo = load_afifo = self.load_afifo
        m.submodules.store_afifo = store_afifo = self.store_afifo
        # TODO : get rid of this
        m.submodules.compute_unit = compute_unit = \
            DomainRenamer(compute_domain)(self.compute_unit)

        # interface_controller <> serial_link
        m.d.comb += serial_link.rx.connect(interface_controller.rx_link)
        m.d.comb += interface_controller.tx_link.connect(serial_link.tx)

        # connect up store unit
        # (interface_controller serial) <> (store_unit serial)
        m.d.comb += interface_controller.rx_ldst.connect(store_unit.rx)
        # (interface_controller upload control) <> (store_unit upload control)
        m.d.comb += store_unit.control.connect(interface_controller.download_control)
        # store unit <> afifo
        m.d.comb += mem.write_port2.connect(store_afifo.compute_domain_wp)
        #  afifo <> memory
        m.d.comb += store_afifo.comm_domain_wp.connect(store_unit.wp)

        # connect up load unit
        # (interface_controller serial) <> (load_unit serial)
        m.d.comb += load_unit.tx.connect(interface_controller.tx_ldst)
        # (interface_controller upload control) <> (load_unit upload control)
        m.d.comb += load_unit.control.connect(interface_controller.upload_control)
        # load unit <> afifo
        m.d.comb += load_unit.rp.connect(load_afifo.comm_domain_rp)
        # afifo <> memory
        m.d.comb += load_afifo.mem_domain_rp.connect(mem.read_port2)

        # compute unit <> memory
        m.d.comb += compute_unit.read_port.connect(mem.read_port1)
        m.d.comb += mem.write_port1.connect(compute_unit.write_port)

        # interface_controller <> status_unit
        m.submodules.start_afifo = start_afifo =\
            AsyncFIFOBuffered(
                width=1, depth=4,
                w_domain=comm_domain,
                r_domain=compute_domain)
        with m.If(start_afifo.w_rdy):
            m.d.comb += start_afifo.w_en.eq(1)
        with m.If(start_afifo.r_rdy):
            m.d.comb += start_afifo.r_en.eq(1)

        m.submodules.status_afifo = status_afifo =\
            AsyncFIFOBuffered(
                width=compute_unit.status.shape().width, 
                depth=4,
                w_domain=comm_domain,
                r_domain=compute_domain)
        with m.If(status_afifo.w_rdy):
            m.d.comb += status_afifo.w_en.eq(1)
        with m.If(status_afifo.r_rdy):
            m.d.comb += status_afifo.r_en.eq(1)

        m.d.comb += compute_unit.start.eq(start_afifo.r_data)
        m.d.comb += start_afifo.w_data.eq(interface_controller.command_compute_start)

        m.d.comb += interface_controller.read_compute_status.eq(status_afifo.r_data)
        m.d.comb += status_afifo.w_data.eq(compute_unit.status)
        
    
        return m

    def ports(self):
        rx = [self.serial_link.rx[sig] for sig in self.serial_link.rx.fields]
        tx = [self.serial_link.tx[sig] for sig in self.serial_link.tx.fields]
        return rx + tx
