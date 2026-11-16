"""Read-only Linux interface and bundled Zeroconf sender diagnostics."""
import fcntl
from pathlib import Path
import socket
import struct


def ipv4_interfaces():
    rows=[]
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        for index,name in socket.if_nameindex():
            address=None
            try:
                reply=fcntl.ioctl(probe.fileno(),0x8915,struct.pack('256s',name.encode()[:15]))
                address=socket.inet_ntoa(reply[20:24])
            except OSError:
                pass  # An existing interface need not have IPv4 yet.
            try:state=(Path('/sys/class/net')/name/'operstate').read_text().strip()
            except OSError:state='unknown'
            rows.append(dict(name=name,index=index,ipv4=address,operstate=state))
    return rows


def default_route_interfaces(path='/proc/net/route'):
    rows=[]
    for line in Path(path).read_text().splitlines()[1:]:
        fields=line.split()
        if len(fields)>3 and fields[1]=='00000000' and int(fields[3],16)&1:
            rows.append(fields[0])
    return sorted(set(rows))


def network_state(zeroconf=None):
    """Sender addresses come from actual bound transports, not desired interfaces.

    Guard private attributes: diagnostics must not affect discovery if a future
    bundled Zeroconf has a different implementation.
    """
    interfaces=ipv4_interfaces()
    result=dict(interfaces=interfaces,default_route_interfaces=default_route_interfaces(),
                bindings_available=False,bound_ipv4=[])
    if zeroconf is None:return result
    senders=getattr(getattr(zeroconf,'engine',None),'senders',None)
    if senders is None:return result
    result['bindings_available']=True
    for sender in tuple(senders):
        if getattr(sender,'is_ipv6',True):continue
        address,_scope=sender.interface_key
        result['bound_ipv4'].append(dict(ipv4=address,
            interface=next((row['name'] for row in interfaces if row['ipv4']==address),None)))
    return result
