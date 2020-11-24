# D2L Linky ERP Module Plugin
#
# Author: Ultrapingu, 2020
#  Some code has been ported (GenerateCRC) or inspired(ReadHeader) from the eedomus module:
#    https://github.com/Zehir/node-red-contrib-eesmart-d2l/blob/15d0a3669afcc314df55a1c2f947e2bda6e6757f/eesmart-d2l.js
#
# Creates and listens on an HTTP socket. Update devices when message received from D2L
#
"""
<plugin key="D2LModule" name="Eesmart D2L ERL Module" author="ultrapingu" version="1.0.0">
    <params>
        <param field="Port" label="Port" width="30px" required="true" default="8008"/>
        <param field="Mode1" label="D2L ID" width="90px" required="true" default=""/>
        <param field="Mode2" label="App Key" width="240px" required="true" default=""/>
        <param field="Mode3" label="IV" width="240px" required="true" default=""/>
        <param field="Mode6" label="Debug" width="100px">
            <options>
                <option label="True" value="Debug"/>
                <option label="False" value="Normal"  default="true" />
            </options>
        </param>
    </params>
</plugin>
"""
import Domoticz
from binascii import hexlify, unhexlify
from Crypto.Cipher import AES
import base64
from datetime import datetime, timezone
import secrets
import json

class BasePlugin:
    enabled = False
    httpServerConn = None
    httpServerConns = {}
    counterHP=None
    counterHC=None
    instantVA=None
    key=None
    IV=None
    lastUpdateHP=None
    lastUpdateHC=None
    lastHP=0
    lastHC=0
    TYPE_COMMANDE_V3_NEED_FIRMWARE_UPDATE = 0x1 #non documenté
    TYPE_COMMANDE_V3_PUSH_JSON = 0x3
    TYPE_COMMANDE_V3_GET_HORLOGE = 0x5

    def __init__(self):
        return

    def uncipher(self, ciphered):
        cipher = AES.new(self.key, AES.MODE_CBC, self.IV)
        return ciphered[:16]+cipher.decrypt(ciphered[16:])

    def cipher(self, plain):
        cipher = AES.new(self.key,AES.MODE_CBC,self.IV)
        return plain[:16]+cipher.encrypt(plain[16:])

    def onStart(self):
        if Parameters["Mode6"] != "Normal":
            Domoticz.Debugging(1)
            DumpConfigToLog()
        self.key=unhexlify(Parameters["Mode2"])
        #self.key=base64.b64decode(Parameters["Mode2"])
        self.IV=unhexlify(Parameters["Mode3"])
        #self.IV=base64.b64decode(Parameters["Mode3"])

        self.httpServerConn = Domoticz.Connection(Name="Server Connection", Transport="TCP/IP", Protocol="None", Port=Parameters["Port"])
        self.httpServerConn.Listen()



    def onConnect(self, Connection, Status, Description):
        if (Status == 0):
            Domoticz.Debug("Connected successfully to: "+Connection.Address+":"+Connection.Port)
        else:
            Domoticz.Debug("Failed to connect ("+str(Status)+") to: "+Connection.Address+":"+Connection.Port+" with error: "+Description)
        LogMessage("Connection: "+str(Connection))
        self.httpServerConns[Connection.Name] = Connection

    def onMessage(self, Connection, Data):
        LogMessage("onMessage called for connection: "+Connection.Address+":"+Connection.Port)
        header = ReadHeader(Data, True)
        if header.idD2L != Parameters["Mode1"]:
            Domoticz.Error("Wrong D2L ID (received {}, configured {}). If you have multiple D2L, add 2 differents hardware".format(header.idD2L, Parameters["Mode1"]))
            return
        if header.frameSize != len(Data):
            Domoticz.Error("Wrong size")
            return
        if header.protocolVersion != 3:
            Domoticz.Log("Protocol version is not 3. Errors may occurs.")
        if header.encryptionMethod != 1:
            Domoticz.Log("Wrong encryption method. Errors may occurs.")
        Data = self.uncipher(bytes(Data))
        header = ReadHeader(Data)
        if header.crc16 != GenerateCRC(Data):
            Domoticz.Error("Invalid CRC")
            return
        if header.isResponse:
            Domoticz.Log("Should be a request")
        if not header.isSuccess:
            Domoticz.Error("Not a success")
        Domoticz.Log(str(header.payloadType)+" "+str(header.payloadSize)+" "+str(header.isRequest)+" "+str(header.isSuccess))
        if header.payloadType == self.TYPE_COMMANDE_V3_PUSH_JSON:
            payload = Data[38:38+header.payloadSize]
            js = Data[38:38+header.payloadSize].decode("utf-8")
            Domoticz.Log(js)
            data = json.loads(js)
            if data["_TYPE_TRAME"] == 'HISTORIQUE':
                if data["OPTARIF"] == "HC..":
                    hp=int(data["HCHP"])
                    intervalHP=0
                    if self.lastUpdateHP != None:
                        intervalHP = (datetime.now()-self.lastUpdateHP).total_seconds()
                    else:
                        CreateDeviceIfNeeded("HP")
                    instantHP=0
                    if intervalHP > 0:
                        instantHP = (hp-self.lastHP)/intervalHP*3600
                        UpdateDevice(Name="HP", nValue=0, sValue=str(round(instantHP))+";"+str(hp))
                    self.lastHP=hp
                    self.lastUpdateHP=datetime.now()

                    hc=int(data["HCHC"])
                    intervalHC=0
                    if self.lastUpdateHC != None:
                        intervalHC = (datetime.now()-self.lastUpdateHC).total_seconds()
                    else:
                        CreateDeviceIfNeeded("HC")
                    instantHC=0
                    if intervalHC > 0:
                        instantHC = (hc-self.lastHC)/intervalHC*3600
                        UpdateDevice(Name="HC", nValue=0, sValue=str(round(instantHC))+";"+str(hc))
                    self.lastHC=hc
                    self.lastUpdateHC=datetime.now()
                    UpdateDevice(Name="Total", nValue=0, sValue=str(round(instantHC+instantHP))+";"+str(hc+hp))
                elif data["OPTARIF"] == "BASE":
                    hp=int(data["BASE"])
                    intervalHP=0
                    if self.lastUpdateHP != None:
                        intervalHP = (datetime.now()-self.lastUpdateHP).total_seconds()
                    else:
                        CreateDeviceIfNeeded("Total")
                    instantHP=0
                    if intervalHP > 0:
                        instantHP = (hp-self.lastHP)/intervalHP*3600
                        UpdateDevice(Name="Total", nValue=0, sValue=str(round(instantHP))+";"+str(hp))
                    self.lastHP=hp
                    self.lastUpdateHP=datetime.now()
                else:
                    Domoticz.Log("Unsupported OPTARIF: "+data["OPTARIF"])
            elif data["_TYPE_TRAME"] == 'STANDARD':
                Domoticz.Log("Standard mode is unsupported")
        elif header.payloadType == self.TYPE_COMMANDE_V3_NEED_FIRMWARE_UPDATE:
            Domoticz.Error("D2L module need a firmware update. Reset it, wait 5 min, connect it on eesmart server, wait for at least an hour, reset it and connect it back to domoticz server.")
            return
        elif header.payloadType == self.self.TYPE_COMMANDE_V3_GET_HORLOGE:
            pass
        else:
            Domoticz.Error("Unknown payload type: "+header.payloadType+". payload="+str(Data[38:38+header.payloadSize]))
        resp = GenerateHorlogeResponse(header)
        resp = self.cipher(resp)
        Connection.Send(resp)
        #Connection.Disconnect()

    def onDisconnect(self, Connection):
        LogMessage("onDisconnect called for connection '"+Connection.Name+"'.")
        LogMessage("Server Connections:")
        for x in self.httpServerConns:
            LogMessage("--> "+str(x)+"'.")
        if Connection.Name in self.httpServerConns:
            del self.httpServerConns[Connection.Name]

#    def onHeartbeat(self):
#        pass



def ReadHeader(Data, onlyUncrypted = False):
    data = type('', (), {})()

    # Version du protocole, toujours égale à 3
    data.protocolVersion = int.from_bytes(Data[0:1], byteorder='little',signed=False)
    # Octet 1 non utilisé
    # Taille de la trame
    data.frameSize = int.from_bytes(Data[2:4], byteorder='little',signed=False)
    # Identifiant du D2L
    data.idD2L = '%012d' % int.from_bytes(Data[4:12], byteorder='little',signed=False)
    # Clef AES utilisé, toujours égale à 1
    data.encryptionMethod = int.from_bytes(Data[12:13], byteorder='little',signed=False) & 0x7
    # octets 13 à 15 réservés
    # L'entête est crypté après le 16eme octet
    if onlyUncrypted:
        return data

    # Nombre aléatoire
    data.randomNumber = Data[16:32]
    # Checksum
    data.crc16 = int.from_bytes(Data[32:34], byteorder='little',signed=False)
    # Taille du payload
    data.payloadSize = int.from_bytes(Data[34:36], byteorder='little',signed=False)
    # Type de payload
    data.payloadType = int.from_bytes(Data[36:37], byteorder='little',signed=False) & 0x7F
    # Commande suivante (force le D2L à exécuter une fonction) (non documenté)
    data.nextQuery = int.from_bytes(Data[37:38], byteorder='little',signed=False) & 0x7F

    # Requete (valeur 0) ou Reponse (valeur 1)
    if ((int.from_bytes(Data[36:37], byteorder='little',signed=False) & 0x80) == 0x80):
        data.isRequest = False
        data.isResponse = True
    else:
        data.isRequest = True
        data.isResponse = False

    # Réussie (valeur 0), Erreur (valeur 1)
    if (int.from_bytes(Data[37:38], byteorder='little',signed=False) & 0x80 == 0x80):
        data.isSuccess = False
        data.isError = True
    else:
        data.isSuccess = True
        data.isError = False

    return data


crcTable = [\
    0x0000, 0xC0C1, 0xC181, 0x0140, 0xC301, 0x03C0,\
    0x0280, 0xC241, 0xC601, 0x06C0, 0x0780, 0xC741,\
    0x0500, 0xC5C1, 0xC481, 0x0440, 0xCC01, 0x0CC0,\
    0x0D80, 0xCD41, 0x0F00, 0xCFC1, 0xCE81, 0x0E40,\
    0x0A00, 0xCAC1, 0xCB81, 0x0B40, 0xC901, 0x09C0,\
    0x0880, 0xC841, 0xD801, 0x18C0, 0x1980, 0xD941,\
    0x1B00, 0xDBC1, 0xDA81, 0x1A40, 0x1E00, 0xDEC1,\
    0xDF81, 0x1F40, 0xDD01, 0x1DC0, 0x1C80, 0xDC41,\
    0x1400, 0xD4C1, 0xD581, 0x1540, 0xD701, 0x17C0,\
    0x1680, 0xD641, 0xD201, 0x12C0, 0x1380, 0xD341,\
    0x1100, 0xD1C1, 0xD081, 0x1040, 0xF001, 0x30C0,\
    0x3180, 0xF141, 0x3300, 0xF3C1, 0xF281, 0x3240,\
    0x3600, 0xF6C1, 0xF781, 0x3740, 0xF501, 0x35C0,\
    0x3480, 0xF441, 0x3C00, 0xFCC1, 0xFD81, 0x3D40,\
    0xFF01, 0x3FC0, 0x3E80, 0xFE41, 0xFA01, 0x3AC0,\
    0x3B80, 0xFB41, 0x3900, 0xF9C1, 0xF881, 0x3840,\
    0x2800, 0xE8C1, 0xE981, 0x2940, 0xEB01, 0x2BC0,\
    0x2A80, 0xEA41, 0xEE01, 0x2EC0, 0x2F80, 0xEF41,\
    0x2D00, 0xEDC1, 0xEC81, 0x2C40, 0xE401, 0x24C0,\
    0x2580, 0xE541, 0x2700, 0xE7C1, 0xE681, 0x2640,\
    0x2200, 0xE2C1, 0xE381, 0x2340, 0xE101, 0x21C0,\
    0x2080, 0xE041, 0xA001, 0x60C0, 0x6180, 0xA141,\
    0x6300, 0xA3C1, 0xA281, 0x6240, 0x6600, 0xA6C1,\
    0xA781, 0x6740, 0xA501, 0x65C0, 0x6480, 0xA441,\
    0x6C00, 0xACC1, 0xAD81, 0x6D40, 0xAF01, 0x6FC0,\
    0x6E80, 0xAE41, 0xAA01, 0x6AC0, 0x6B80, 0xAB41,\
    0x6900, 0xA9C1, 0xA881, 0x6840, 0x7800, 0xB8C1,\
    0xB981, 0x7940, 0xBB01, 0x7BC0, 0x7A80, 0xBA41,\
    0xBE01, 0x7EC0, 0x7F80, 0xBF41, 0x7D00, 0xBDC1,\
    0xBC81, 0x7C40, 0xB401, 0x74C0, 0x7580, 0xB541,\
    0x7700, 0xB7C1, 0xB681, 0x7640, 0x7200, 0xB2C1,\
    0xB381, 0x7340, 0xB101, 0x71C0, 0x7080, 0xB041,\
    0x5000, 0x90C1, 0x9181, 0x5140, 0x9301, 0x53C0,\
    0x5280, 0x9241, 0x9601, 0x56C0, 0x5780, 0x9741,\
    0x5500, 0x95C1, 0x9481, 0x5440, 0x9C01, 0x5CC0,\
    0x5D80, 0x9D41, 0x5F00, 0x9FC1, 0x9E81, 0x5E40,\
    0x5A00, 0x9AC1, 0x9B81, 0x5B40, 0x9901, 0x59C0,\
    0x5880, 0x9841, 0x8801, 0x48C0, 0x4980, 0x8941,\
    0x4B00, 0x8BC1, 0x8A81, 0x4A40, 0x4E00, 0x8EC1,\
    0x8F81, 0x4F40, 0x8D01, 0x4DC0, 0x4C80, 0x8C41,\
    0x4400, 0x84C1, 0x8581, 0x4540, 0x8701, 0x47C0,\
    0x4680, 0x8641, 0x8201, 0x42C0, 0x4380, 0x8341,\
    0x4100, 0x81C1, 0x8081, 0x4040\
]

def GenerateCRC(buffer):
    global crcTable
    data = buffer[0:32] + buffer[34:];

    crc = 0xFFFF
    for b in data:
        crc = crcTable[(b ^ crc) & 0xFF] ^ (crc >> 8 & 0xFF)
    return (crc ^ 0x0000) & 0xFFFF

def GenerateHorlogeResponse(header):
    buffer = 0x3.to_bytes(1, byteorder="little", signed=False)                       #0(1)  : protocol version
    buffer += 0x0.to_bytes(1, byteorder="little", signed=False)                      #1(1)  : unused
    #following value will be replace at the end of method
    buffer += 0x0.to_bytes(2, byteorder="little", signed=False)                      #2(2)  : frame size
    buffer += int(Parameters["Mode1"]).to_bytes(8, byteorder="little", signed=False) #4(8)  : ID D2L
    buffer += 0x1.to_bytes(1, byteorder="little", signed=False)                      #12(1) : encryption method (bit 0-2, always 1)
    buffer += 0x0.to_bytes(3, byteorder="little", signed=False)                      #13(3) : unused
    buffer += secrets.token_bytes(16)                                                #16(16): random number
    #following value will be replace at the end of method
    buffer += 0x0.to_bytes(2, byteorder="little", signed=False)                      #32(2) : crc16
    buffer += 0x4.to_bytes(2, byteorder="little", signed=False)                      #34(2) : payload size

    payloadType = header.payloadType+0x80
    buffer += payloadType.to_bytes(1, byteorder="little", signed=False)              #36(1) : payload type + response(bit7=1 if response)
    buffer += 0x0.to_bytes(1, byteorder="little", signed=False)                      #37(1) : next command + success (bit7=1 if error)
    buffer += GetHorloge().to_bytes(4, byteorder="little", signed=False)             #38(4) : payload (nb seconds since 2016/01/01 00:00:00 UTC)

    missingBytes = 16 - len(buffer) % 16
    if (missingBytes > 0):
        buffer += 0x0.to_bytes(missingBytes, byteorder="little", signed=False)

    # replace frame size
    buffer=buffer[:2] + len(buffer).to_bytes(2, byteorder="little", signed=False) + buffer[4:]
    # replace crc
    buffer=buffer[:32] + GenerateCRC(buffer).to_bytes(2, byteorder="little", signed=False) + buffer[34:]

    return buffer;

def GetHorloge():
    return int((datetime.now(timezone.utc)-datetime(2016, 1, 1, tzinfo=timezone.utc)).total_seconds())


NameToUnit = {
  "HP":1,
  "HC":2,
  "Total":3
}

def CreateDeviceIfNeeded(Name):
    if not Name in NameToUnit:
        Domoticz.Error("Device name not defined")
        return None
    i=NameToUnit[Name]

    if i in Devices:
        dev=Devices[i]
    else:
        dev=Domoticz.Device(Name=Name, Unit=i, TypeName="kWh")
        dev.Create()
    return dev

def UpdateDevice(Name, nValue, sValue):
    dev=CreateDeviceIfNeeded(Name)
    if dev is None:
        return
    dev.Update(nValue, sValue)

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)

def onMessage(Connection, Data):
    global _plugin
    _plugin.onMessage(Connection, Data)

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

#def onHeartbeat():
#    global _plugin
#    _plugin.onHeartbeat()

# Generic helper functions
def LogMessage(Message):
    if Parameters["Mode6"] == "Normal":
        Domoticz.Log(Message)
    elif Parameters["Mode6"] == "Debug":
        Domoticz.Log(Message)

def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Log( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return

def DumpHTTPResponseToLog(httpDict):
    if isinstance(httpDict, dict):
        Domoticz.Log("HTTP Details ("+str(len(httpDict))+"):")
        for x in httpDict:
            if isinstance(httpDict[x], dict):
                Domoticz.Log("--->'"+x+" ("+str(len(httpDict[x]))+"):")
                for y in httpDict[x]:
                    Domoticz.Log("------->'" + y + "':'" + str(httpDict[x][y]) + "'")
            else:
                Domoticz.Log("--->'" + x + "':'" + str(httpDict[x]) + "'")
