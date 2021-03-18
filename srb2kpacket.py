import socket
import struct
from struct import pack, unpack
from datetime import datetime
from datetime import timedelta
import html
import re

class SRB2K:
    def php_unpack(self, format, values):
        n = 0
        format_array = format.split('/')
        output = {}
        for data_format in format_array:
            unpack_param = ""
            unpack_param_len = 0
            for c in data_format:
                unpack_param += c
                unpack_param_len = unpack_param_len + 1
                if not c.isnumeric() and c != "*": break
            if "*" in unpack_param:
                unpack_param = str(len(values)-n) + unpack_param[-1:]
            data = struct.unpack_from(unpack_param,values,n)
            data_format_name = data_format[unpack_param_len:]
            output[data_format_name] = data[0]
            
            n += struct.calcsize(unpack_param)
        return output
            

    def bytes_to_int(self, bytes, s=False):
        return int.from_bytes(bytes, byteorder='little', signed=s)

    def cstrsize(self, s, l = 0, n = None):
        if type(s) is tuple: s = s[0]
        length = len(s) - l
        if (( length ) < 0):
            return 0
        # We can't substr outside of length.
        if (n is not None and n < length):
            s = s[l:l+n]
            l = 0
            length = n
        n = s.find(b"\0", l)
        return length if n == -1 else n - l + 1

    def cstr (self, s, l = 0, n = None):
        if type(s) is tuple: s = s[0]
        n = self.cstrsize(s, l, n)
        # Check that we haven't been truncated.
        if not ord(chr(s[l + ( n-1 )])):
            n = n - 1
        new_s = bytearray()
        for c in s:
            if c == 0x7F or c <= 0x19 or c >= 0x90: new_s.append(0x00)
            else: new_s.append(c)
        return (new_s[l:l+n]).decode('utf-8','backslashreplace').replace('\x00','')

    colors = [
        'inherit',
        '#df00df',
        '#ffff0f',
        '#69e046',
        '#7373ff',
        '#ff3f3f',
        '#a7a7a7',
        '#ff9736',
        '#55c8ff',
        '#cf7fcf',
        '#d7bb43',
        '#c7e494',
        '#c4c4e1',
        '#f3a3a3',
        '#bf7b4b',
        '#ffc7a7',
    ]
    TICRATE            = 35
    GT_COOP            = 0
    GT_COMPETITION     = 1
    GT_RACE            = 2
    GT_MATCH           = 3
    GT_TEAMMATCH       = 4
    GT_TAG             = 5
    GT_HIDEANDSEEK     = 6
    GT_CTF             = 7
    GF_REDFLAG         = 1
    GF_BLUEFLAG        = 2
    PT_ASKINFO         = 12
    PT_SERVERINFO      = 13
    PT_PLAYERINFO      = 14
    PT_TELLFILESNEEDED = 32
    PT_MOREFILESNEEDED = 33
    SV_SPEEDMASK       = 0x03
    SV_LOTSOFADDONS    = 0x20
    SV_DEDICATED       = 0x40
    SV_PASSWORD        = 0x80
    NETFIL_WONTSEND    = 32
    NETFIL_WILLSEND    = 16
    pkformats = {
        PT_SERVERINFO: {
            'format':
            'B_255/'           +
            'Bpacketversion/'  +
            '16sapplication/'  +
            'Bversion/'        +
            'Bsubversion/'     +
            'Bnumberofplayer/' +
            'Bmaxplayer/'      +
            'Bgametype/'       +
            'Bmodifiedgame/'   +
            'Bcheatsenabled/'  +
            'Bisdedicated/'    +
            'Bfileneedednum/'  +
            'Itime/'           +
            'Ileveltime/'      +
            '32sservername/'   +
            '8smapname/'       +
            '33smaptitle/'     +
            '16smapmd5/'       +
            'Bactnum/'         +
            'Biszone/'         +
            '256shttpsource/'  +
            '*sfileneeded',

            'strings': [
                'application',
                #'gametypename',
                'servername',
                'mapname',
                'maptitle',
                'httpsource',
            ],

            'minimum': 151,
        },
        PT_PLAYERINFO: {
            'format':
            'Bnode/'           +
            '22sname/'         +
            '4saddress/'       +
            'Bteam/'           +
            'Bskin/'           +
            'Bdata/'           +
            'Iscore/'          +
            'Htimeinserver',

            'strings': [
                'name'
            ],

            'minimum': 36,
        },
        PT_MOREFILESNEEDED: {
            'format':
            'Ifirst/'          +
            'Bnum/'            +
            'Bmore/'           +
            '*sfiles',

            'minimum': 6,
        },
    }
    MAX_WADPATH        = 512

    so = None
    pk = {}
    #s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
    addr = ''
    port = 5029
    timeout = 5
    retries = 0

    lotsofaddons = None
    fileneedednum = None
    fileneeded = None

    def Zonetitle(self, pk):
        maptitle = pk['maptitle']
        if (pk['iszone']):
            maptitle += ' Zone'
        if (pk['actnum']):
            maptitle += ' ' + pk['actnum']
        return maptitle.strip()

    def Unkartvars (self, info, pk):
        c = pk['isdedicated']

        self.lotsofaddons = bool( c & self.SV_LOTSOFADDONS )
        info['lotsofaddons'] = bool(self.lotsofaddons)

        if (pk['gametype'] == self.GT_RACE):
            speeds = [
                'Easy',
                'Normal',
                'Hard',
            ]
            speed = speeds[( c & self.SV_SPEEDMASK )]
            info['kartspeed'] = ( speed if speed else 'Too fast' )
        info['dedicated'] = bool( c & self.SV_DEDICATED )
        info['password-protected'] = bool( c & self.SV_PASSWORD  )

    def Checksum(self, p, l):
        n = len(p) - l
        c = 0x1234567
        for i in range(n):
            c += ord(chr(p[l + i])) * (i + 1)
        return c

    def Packet (self, pk):
        u = ''
        if pk['type'] == self.PT_ASKINFO:
            # 1 byte version and 4 byte time */
            u = pack('5x')
        elif self.PT_TELLFILESNEEDED:
            u = pack('I',pk['filesneedednum'])
        # 1 byte ack and 1 byte ackreturn, finally 1 byte padding */
        buf = pack('xxBx', pk['type']) + u
        return pack('I', self.Checksum(buf, 0)) + buf

    def Unpk (self, pk, n = 0):
        pkf = self.pkformats[pk['type']]
        # I can get away with just 'minimum' for now because there aren't any
        # variable length packets in array format. That sounds stupid anyway.
        n = n * pkf['minimum']
        if (n + pkf['minimum'] > len(pk['buffer'])):
            return False
        t = self.php_unpack(pkf['format'], pk['buffer'][n:])
        if 'strings' in pkf:
            for s in pkf['strings']:
                t[s] = self.cstr(t[s])
        return t

    def Unpacket (self, p, type, unpk = True):
        p = p[0]
        n = len(p)
        if (n < 8): # Header
            print('header')
            return False
        if (self.bytes_to_int(p[:4]) != self.Checksum(p, 4)): # Checksum mismatch
            print('bad checksum')
            return False
        self.pk['type'] = ord(chr(p[6]))
        if (self.pk['type'] != type):
            print('line 214')
            return False
        pkf = self.pkformats[self.pk['type']]
        if not pkf:
            print('line 218')
            return False
        if (n < pkf['minimum']):
            print('smaller than minimum')
            return False
        self.pk['buffer'] = p[8:]
        if (unpk):
            self.pk = {**self.pk, **self.Unpk(self.pk)}
            del self.pk['buffer']
        return self.pk

    def Unfileneeded (self, fileinfo, fileneedednum, fileneeded):
        l = 0
        pk = {}
        for i in range(fileneedednum):
            pk = self.php_unpack(
                'Bstatus/' +
                'Isize',
                fileneeded[l:])
            l = l + 5

            pk['name'] = self.cstr(fileneeded, l, self.MAX_WADPATH)
            l = l + self.cstrsize(fileneeded, l, self.MAX_WADPATH)

            pk['md5sum'] = fileneeded[l:l+16].hex()
            l = l + 16

            pk['toobig'] =  bool(not ( pk['status'] & self.NETFIL_WILLSEND ))
            pk['download'] = bool(not ( pk['toobig'] or ( pk['status'] & self.NETFIL_WONTSEND ) ))

            del pk['status']

            fileinfo.append(pk)
        return fileinfo

    def Send (self,pk):
        buf = self.Packet(pk)
        return self.so.sendto(buf, (self.addr, self.port))

    def Settimeoutopt (self):
        return self.so.settimeout(self.timeout)

    def Sendto (self,pk):
        if self.so is None:
            self.so = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
        self.Settimeoutopt()
        return self.Send(pk)

    def Read (self, type, unpk = True):
        tries = -1
        pk = False
        while not pk and tries < self.retries:
            buf = self.so.recvfrom(1450)
            if not buf:
                return False
            pk = self.Unpacket(buf, type, unpk)
            tries = tries + 1
        return pk

    def SetTimeout (self,ms):
        self.timeout = int(ms / 1000),
        if (self.so):
            return self.Settimeoutopt()
        else:
            return True

    def SetRetries (n):
        self.retries = n

    def Close (self):
        if (self.so):
            self.so.close()
            self.so = None

    def Ask(self):
        return self.Sendto({'type': self.PT_ASKINFO})

    def Info(self):
        starttime = datetime.now()
        self.pk = self.Read(self.PT_SERVERINFO)
        if not self.pk:
            return False
        stoptime = datetime.now() - starttime
        self.fileneedednum = self.pk['fileneedednum']
        self.fileneeded    = self.pk['fileneeded']

        version    = self.pk['version']
        subversion = self.pk['subversion']
        
        t = {}

        # SRB2Kart 1.0.4 and 1.10.0
        #if (( version == 100 && subversion == 4 ) or
        #    version == 110)
        #{
        self.Unkartvars(t, self.pk)
        #}
        #else
        #{
        #    copy_bool(t['dedicated'], pk['isdedicated'])
        #    lotsofaddons = FALSE
        #}

        t['ping'] = int((stoptime.days * 24 * 60 * 60 + stoptime.seconds) * 1000 + stoptime.microseconds / 1000.0)
        t['version'] = {
            'major': int(version / 100),
            'minor': version % 100,
            'patch': subversion,
        }
        t['version']['name'] = self.pk['application']

        t['servername'] = self.pk['servername']

        t['players'] = {
            'count': self.pk['numberofplayer'],
            'max': self.pk['maxplayer'],
        }
        t['gametype'] = 'Unknown'
        if self.pk['gametype'] == 2: t['gametype'] = 'Race'
        elif self.pk['gametype'] == 3: t['gametype'] = 'Battle'
        #t['gametype'] = pk['gametype']


        t['mods'] =   bool(self.pk['modifiedgame'])
        t['cheats'] = bool(self.pk['cheatsenabled'])

        t['level'] = {
            'seconds': self.pk['leveltime'] / self.TICRATE,
            'name'   : self.pk['mapname'],
            'title'  : self.Zonetitle(self.pk),
            'md5sum' : self.pk['mapmd5'].hex(),
        }

        if str(self.pk['httpsource'][-1:]) != '/': t['httpsource'] = self.pk['httpsource']+'/'    
        else: t['httpsource'] = self.pk['httpsource']

        info = t
        del t
        mpk = self.Read(self.PT_PLAYERINFO, False)

        if not mpk:
            return info

        teams = {
            self.GF_REDFLAG: 'Red',
            self.GF_BLUEFLAG: 'Blue',
            0                 : 'Playing',
            255               : 'Spectator',
        }

        info['players']['list'] = []

        for i in range(32):
            t = {}
            self.pk = self.Unpk(mpk, i)
            if not self.pk:
                break
            if (self.pk['node'] < 255):
                t['name']    = self.pk['name']
                team = teams[self.pk['team']]
                t['team']    = ( team if team else 'Unknown' )
                t['rank' if (version == 100 or version == 110)
                     else 'score' ] = self.pk['score']
                t['seconds'] = self.pk['timeinserver']

                info['players']['list'].append(t)

        return info

    def Fileinfo (self) :
        fileinfo = []
        fileinfo = self.Unfileneeded(fileinfo, self.fileneedednum, self.fileneeded);

        if (self.lotsofaddons):
            start = self.fileneedednum;
            self.pk['more'] = True
            while self.pk['more']:
                if (not self.Send({
                    'type'           : self.PT_TELLFILESNEEDED,
                    'filesneedednum' : start,
                })):
                    break;
                self.pk = self.Read(self.PT_MOREFILESNEEDED)
                if not self.pk:
                    break;
                start += self.pk['num']
                fileinfo = self.Unfileneeded(fileinfo, self.pk['num'], self.pk['files'])
        return fileinfo

    def Colorize (self,s) :
        #Probably not the pinnacle of performance.
        codes = ["\\x80","\\x81","\\x82","\\x83","\\x84","\\x85","\\x86","\\x87","\\x88","\\x89","\\x8a","\\x8b","\\x8c","\\x8d","\\x8e","\\x8f",]
        #Remove anything that is not printable ASCII and sanitize!
        s = html.escape(s)
        for i in range(0x10):
            s = s.replace(codes[i],
                '</span><span style="color:' + self.colors[i] + ';">')
        s = '<span style="color:' + self.colors[0] + '">' + s + '</span>'
        
        #Doing this backward for a good reason; so that higher numbers get a
        #chance to be matched!
        #Not necessary anymore though...
        #for (i = 0x0F; i >= 0x00; --i)

        return s

    def Main(self, user_addr, user_port = 5029):
        self.addr = user_addr
        self.port = user_port
        self.Ask()
        info = self.Info()
        info['servername'] = self.Colorize(info['servername'])
        info['addons'] = self.Fileinfo()
        self.Close()
        return info