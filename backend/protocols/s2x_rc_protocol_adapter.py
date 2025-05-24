from protocols.base_protocol_adapter import BaseProtocolAdapter
import socket

class S2xRCProtocolAdapter(BaseProtocolAdapter):
    """Protocol adapter for S2x drones (S20, S29)"""
    
    def __init__(self, drone_ip, control_port=8080):
        self.drone_ip = drone_ip
        self.control_port = control_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.debug_packets = False
        self.packet_counter = 0
        
    def build_control_packet(self, drone_model):
        """Build a control packet for the S2x protocol"""
        pkt = bytearray(20)
        pkt[0] = 0x66
        pkt[1] = drone_model.speed & 0xFF

        # Remap from constrained range to full 0-255 range
        pkt[2] = int(self._remap_to_full_range(drone_model.roll, drone_model)) & 0xFF
        pkt[3] = int(self._remap_to_full_range(drone_model.pitch, drone_model)) & 0xFF  
        pkt[4] = int(self._remap_to_full_range(drone_model.throttle, drone_model)) & 0xFF
        pkt[5] = int(self._remap_to_full_range(drone_model.yaw, drone_model)) & 0xFF

        # Byte 6 for command flags
        pkt[6] = 0x00
        
        # Handle one-shot flags
        if drone_model.takeoff_flag:
            pkt[6] |= 0x01
        if drone_model.land_flag:
            pkt[6] |= 0x02
        if drone_model.stop_flag:
            pkt[6] |= 0x04

        # Byte 7 - base value 0x0a
        pkt[7] = 0x0a
        
        # Record flag
        if drone_model.record_state:
            pkt[7] |= (drone_model.record_state << 2)

        # bytes 8-17 are zero-filled

        # Calculate checksum (bytes 2-17)
        chk = 0
        for i in range(2, 18):
            chk ^= pkt[i]
        pkt[18] = chk & 0xFF
        pkt[19] = 0x99

        # Clear one-shot flags after building packet
        drone_model.takeoff_flag = False
        drone_model.land_flag = False
        drone_model.stop_flag = False

        return bytes(pkt)
        
    def send_control_packet(self, packet):
        """Send the control packet to the drone"""
        self.sock.sendto(packet, (self.drone_ip, self.control_port))
        
        # Log packet details if debug is enabled
        if self.debug_packets:
            self.packet_counter += 1
            
            # Print full packet hex dump
            hex_dump = ' '.join(f'{b:02x}' for b in packet)
            print(f"Packet #{self.packet_counter}: {hex_dump}")
            
            # Print decoded controls
            print(f"  Controls: R:{packet[2]} P:{packet[3]} T:{packet[4]} Y:{packet[5]}")
            
            # Print flags
            flags6 = packet[6]
            flags7 = packet[7]
            flags_desc = []
            if flags6 & 0x01: flags_desc.append("TAKEOFF")
            if flags6 & 0x02: flags_desc.append("LAND")
            if flags6 & 0x04: flags_desc.append("STOP")
            if flags7 & 0x01: flags_desc.append("HEADLESS")
            if flags7 & 0x04: flags_desc.append("RECORD")
            
            print(f"  Flags: {flags_desc}")
            print(f"  Checksum: 0x{packet[18]:02x}")
            print()
    
    def toggle_debug(self):
        """Toggle debug packet logging"""
        self.debug_packets = not self.debug_packets
        return self.debug_packets
        
    def _remap_to_full_range(self, value, model):
        """Remap value from constrained range to full 0-255 range for sending to drone"""
        if value >= model.center_value:
            # Map center...max_control to 128...255
            return 128.0 + (value - model.center_value) * (255.0 - 128.0) / (model.max_control_value - model.center_value)
        else:
            # Map min_control...center to 0...128
            return (value - model.min_control_value) * 128.0 / (model.center_value - model.min_control_value)