# D2L Linky ERP Module Plugin
#
# Author: Ultrapingu, 2020
#  Some code has been ported (GenerateCRC) or inspired(ReadHeader) from the eedomus module:
#    https://github.com/Zehir/node-red-contrib-eesmart-d2l/blob/15d0a3669afcc314df55a1c2f947e2bda6e6757f/eesmart-d2l.js
#
# Creates and listens on an HTTP socket. Update devices when message received from D2L
#
"""
<plugin key="D2LModule" name="Eesmart D2L ERL Module" author="ultrapingu" version="1.2.0">
    <description>
        <h2>Eesmart D2L ERL Module</h2><br/>
        <h3>Paramètres</h3>
        <ul style="list-style-type:square">
            <li>Port: Port IP à configurer dans le module (l'adresse IP étant celle du serveur Domoticz)</li>
            <li>App Key: La clef applicative correspondant à votre module nécessaire au déchiffrement des trames du module (32 caractères, nombre hexadécimal)</li>
            <li>IV: Le vecteur d'initialisation (initialization) AES correspondant à votre module nécessaire au déchiffrement des trames du module (32 caractères, nombre hexadécimal)</li>
            <li>Standard Mode Config : Correspondance champs JSON signification pour le mode standard.<br/>
                 En mode standard, il semble que la valeur des champs varie d'un fournisseur à un autre.
                 Il est donc plus simple de proposer de configurer la signification des champs.<br/>
                 Il faut indiquer 4 champs séparés par des ; avec dans l'ordre, les compteurs suivants :<br/>
                 <pre>Conso Heures Pleines;Conso Heures Creuses;Prod Heures Pleines;Prod Heures Creuses</pre>
                 Valeurs typiques :
                 <ul>
                     <li>Avec production :</li>
                     <ul>
                         <li>EDF contrat BASE : "EASF01;;EAIT;</li>
                         <li>EDF contrat HP/HC : "EASF02;EASF01;EAIT;</li>
                         <li>EDF contrat HC Week end : "EASF02;EASF01+EASF03;EAIT;</li>
                     </ul>
                     <li>Sans production : Laissez les 2 derniers champs vides</li>
                 </ul>
            </li>
            <li>Additional Fields: Des champs du message json à ajouter en custom sensor. Les champs doivent être séparés par un ; et suffixé de @ suivi de l'unité du champ (si l'unité est TEXT, le champ sera de type "Texte"). Les sommes de champs sont gérées (il suffit de séparer les noms des champs par un +). Exemple: "ADIR1@A;HCHP+HCHC@kWh;_ID_D2L@TEXT"</li>
            <li>Debug: All/Communication/None. Communication permet de ne loguer que les données envoyées par le module</li>
        </ul>
        <h3>Dispositifs créés</h3>
        <ul style="list-style-type:square">
            <li>Intensité : Monophasé: une intensité (IINST), Triphasé: 3 intensités combiné en un dispositif (IINST1, IINST2, IINST3)</li>
            <li>Charge électrique : Pourcentage de charge du compteur (IINST/ISOUSC ou max(IINST1,IINST2,IINST3)/ISOUSC</li>
            <li>En fonction du contrat :</li>
            <ul>
                <li>Contrat BASE :</li>
                <ul>
                    <li>Total : compteur kWh</li>
                </ul>
                <li>Contrat HC.. :</li>
                <ul>
                    <li>HP/HC: de type P1 Smart Sensor contenant les toutes les infos des 3 autres compteurs</li>
                </ul>
            </ul>
        </ul>
    </description>
    <params>
        <param field="Port" label="Port" width="30px" required="true" default="8008"/>
        <!--param field="Mode1" label="D2L ID" width="90px" required="true" default=""/-->
        <param field="Mode2" label="App Key" width="240px" required="true" default=""/>
        <param field="Mode3" label="IV" width="240px" required="true" default=""/>
        <param field="Mode4" label="Standard Mode Config" width="240px" required="false" default="EASF02;EASF01+EASF03;EAIT;"/>
        <param field="Mode5" label="Additional Fields" width="240px" required="false" default=""/>
        <param field="Mode6" label="Debug" width="120px">
            <options>
                <option label="All" value="All"/>
                <option label="Communication" value="Comm" />
                <option label="None" value="None" default="true" />
            </options>
        </param>
    </params>
</plugin>
"""
import Domoticz
from binascii import hexlify, unhexlify
from Crypto.Cipher import AES
import base64
from datetime import datetime, timezone, timedelta
import secrets
import json
import re
import os

# Si DEBUG_FRAME_ENABLED==True, les trames du fichiers frame_examples.txt sont lues au démarrage du plugin (test regression). 
# Les devices crés/mis à jour sont différents de ceux utilisé en prod afin de ne pas collecter des données de debug sur les dispositifs de prod dans la base domoticz.
# Faire attention à ce que la ligne ci-dessous soit bien DEBUG_FRAME_ENABLED=False avant de commiter.
DEBUG_FRAME_ENABLED=False

# TODO: supprimer la classe (passer en tout fonction + variable globale)
class BasePlugin:
    enabled = False
    httpServerConn = None
    httpServerConns = {}
    key = None
    IV = None
    lastUpdate = None
    lastIdD2L = None
    incompleteMessage = None
    triphase = False
    lastValues = None
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
        if not re.match("^20[0-9][0-9]\\..+", Parameters["DomoticzVersion"]):
            Domoticz.Error("Domoticz version must be 2020.1 or above (version: {}). Plugin has not been tested with older version and may not work. Ignore this if you're running a beta version.".format(Parameters["DomoticzVersion"]))
        if Parameters["Mode6"] == "All":
            Domoticz.Debugging(1)
            DumpConfigToLog()
        self.key=unhexlify(Parameters["Mode2"])
        #self.key=base64.b64decode(Parameters["Mode2"])
        self.IV=unhexlify(Parameters["Mode3"])
        #self.IV=base64.b64decode(Parameters["Mode3"])
        CreateImagesIfNeeded()

        self.httpServerConn = Domoticz.Connection(Name="Server Connection", Transport="TCP/IP", Protocol="None", Port=Parameters["Port"])
        self.httpServerConn.Listen()
        if DEBUG_FRAME_ENABLED:
            savedConfigStandard = Parameters["Mode4"]
            savedAdditionalFields = Parameters["Mode5"]
            debugFrames=ReadDebugFramesFile()
            for f in debugFrames:
                Parameters["Mode4"] = f[1]
                Parameters["Mode5"] = f[2]
                data = json.loads(f[0])
                self.lastValues = None
                self.lastUpdate = None
                self.processJson(data)
                self.lastUpdate -= timedelta(seconds=60)
                self.processJson(data) #second time to really update device 
            Parameters["Mode4"] = savedConfigStandard
            Parameters["Mode5"] = savedAdditionalFields

        self.lastValues = None
        self.lastUpdate = None
        self.lastIdD2L = None
        self.triphase = False
        self.incompleteMessage = None
        adLastValues = {}

    def onConnect(self, Connection, Status, Description):
        if (Status == 0):
            LogMessage("Connected successfully to: "+Connection.Address+":"+Connection.Port)
        else:
            Domoticz.Error("Failed to connect ("+str(Status)+") to: "+Connection.Address+":"+Connection.Port+" with error: "+Description)
        self.httpServerConns[Connection.Name] = Connection
        self.incompleteMessage = None

    def onMessage(self, Connection, Data):
        if self.incompleteMessage != None:
            Data = self.incompleteMessage + Data;
        header = ReadHeader(Data, True)
        if header.frameSize > len(Data): # Attendre que le message soit complet
            self.incompleteMessage = Data
            return
        elif header.frameSize < len(Data):
            Domoticz.Error("Wrong frame size (expected: {}, received: {})".format(header.frameSize, len(Data)))
            return
        else:
            self.incompleteMessage = None
        if self.lastIdD2L != None and header.idD2L != self.lastIdD2L:
            Domoticz.Error("Multiple D2L IDs detected (received {}, last received {}). If you have multiple D2L, add 2 hardwares with different ports".format(header.idD2L, self.lastIdD2L))
            return
        self.lastIdD2L = header.idD2L
        LogMessage("Message received from module "+header.idD2L)
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
            Domoticz.Error("The module sends a response, it is not a normal behaviour.")
        if header.isError:
            Domoticz.Error("D2L returns that last command/resquest was not a success.")
        if header.payloadType == self.TYPE_COMMANDE_V3_PUSH_JSON:
            payload = Data[38:38+header.payloadSize]
            js = Data[38:38+header.payloadSize].decode("utf-8")
            if Parameters["Mode6"] == "Comm" or Parameters["Mode6"] == "All":
                 Domoticz.Log("JSON Frame received: "+js)
            data = json.loads(js)
            self.processJson(data)
        elif header.payloadType == self.TYPE_COMMANDE_V3_NEED_FIRMWARE_UPDATE:
            Domoticz.Error("D2L module need a firmware update. Reset it, wait 5 min, connect it on eesmart server, wait for at least an hour, reset it and connect it back to domoticz server.")
            return
        elif header.payloadType == self.TYPE_COMMANDE_V3_GET_HORLOGE:
            pass
        else:
            Domoticz.Error("Unknown payload type: "+header.payloadType+". payload="+str(Data[38:38+header.payloadSize]))
        resp = GenerateHorlogeResponse(header)
        resp = self.cipher(resp)
        Connection.Send(resp)

    def processJson(self, data):
        if data["_TYPE_TRAME"] == 'HISTORIQUE':
            iinst1=int(data["IINST1"])
            iinst2=int(data["IINST2"])
            iinst3=int(data["IINST3"])
            isousc=int(data["ISOUSC"])
            if self.triphase or iinst2 > 0 or iinst3 > 0:
                self.triphase=True
                UpdateDevice("Intensité (triphasé)", 0, str(iinst1)+";"+str(iinst2)+";"+str(iinst3))
                UpdateDevice("Charge Electrique", 0, str(round(max(iinst1,iinst2,iinst3)/isousc*100)))
            else:
                UpdateDevice("Intensité", 0, str(iinst1))
                UpdateDevice("Charge Electrique", 0, str(round(iinst1/isousc*100)))

            if data["OPTARIF"] == "HC..":
                hp=int(data["HCHP"])
                hc=int(data["HCHC"])
                instantHP = None
                instantHC = None
                if self.lastValues != None and self.lastUpdate != None:
                    instantHP = self.computeInstant(self.lastValues[0], hp)
                    instantHC = self.computeInstant(self.lastValues[1], hc)
                    UpdateDevice(Name="HP/HC", nValue=0, sValue=str(hp)+";"+str(hc)+";0;0;"+str(round(instantHC+instantHP))+";0")
                self.lastValues = [hp, hc]
            elif data["OPTARIF"] == "BASE":
                hp=int(data["BASE"])
                instantHP = None
                if self.lastValues != None and self.lastUpdate != None:
                    instantHP = self.computeInstant(self.lastValues[0], hp)
                    UpdateDevice(Name="Total", nValue=0, sValue=str(round(instantHP))+";"+str(hp))
                else:
                    CreateDeviceIfNeeded("Total")
                self.lastValues = [hp]
            else:
                Domoticz.Error("Unsupported OPTARIF: "+data["OPTARIF"])
        elif data["_TYPE_TRAME"] == 'STANDARD':
            iinst1=0
            if "IRMS1" in data and data["IRMS1"].strip() != "":
                iinst1=int(data["IRMS1"])
            iinst2=0
            if "IRMS2" in data and data["IRMS2"].strip() != "":
                iinst2=int(data["IRMS2"])
            iinst3=0
            if "IRMS3" in data and data["IRMS3"].strip() != "":
                iinst3=int(data["IRMS3"])
            sinsts=int(data["SINSTS"])
            pcoup=int(data["PCOUP"])
            UpdateDevice("Charge Electrique", 0, str(round(sinsts/10/pcoup, 1)))
            if self.triphase or iinst2 > 0 or iinst3 > 0:
                UpdateDevice("Intensité (triphasé)", 0, str(iinst1)+";"+str(iinst2)+";"+str(iinst3))
            else:
                UpdateDevice("Intensité", 0, str(iinst1))
            
            # TODO: Preparser la config mode standard
            fields = Parameters["Mode4"].split(';')
            nbFields = 0
            firstField = None
            for f in fields:
                if f.strip() != "":
                    nbFields += 1
                    firstField = f
                    continue
            if nbFields == 0:
                Domoticz.Error("Standard Mode Config is empty")
            elif nbFields == 1:
                vals = [0]
                vals[0] = GetNumericValue(firstField, data)
                instant = None
                if self.lastValues != None and self.lastUpdate != None:
                    instant = self.computeInstant(self.lastValues[0], vals[0])
                    UpdateDevice("Total", 0, str(round(instant)) + ";" + str(int(vals[0])))
                else:
                    CreateDeviceIfNeeded("Total")
                self.lastValues = vals
            else:
                sVal=""
                vals = [0,0,0,0]
                i = 0
                for f in fields:
                    if f.strip() != "":
                        vals[i] = int(GetNumericValue(f, data))
                        sVal += str(vals[i])
                    else:
                        sVal += "0"
                    i+=1
                    sVal += ";"
                while i<4:
                    sVal += "0;"
                    i+=1
                if self.lastValues != None and self.lastUpdate != None:
                    sVal += str(int(self.computeInstant(self.lastValues[0]+self.lastValues[1], vals[0]+vals[1])))
                    sVal += ";"
                    sVal += str(int(self.computeInstant(self.lastValues[2]+self.lastValues[3], vals[2]+vals[3])))
                    UpdateDevice("HP/HC", 0, sVal)
                else:
                    CreateDeviceIfNeeded("HP/HC")
                    
                self.lastValues = vals
        UpdateAdditionalDevices(data)
        self.lastUpdate = datetime.now()

    def computeInstant(self, oldValue, newValue):
        if self.lastUpdate != None and oldValue != None:
            interval = (datetime.now() - self.lastUpdate).total_seconds()
            instant = (newValue - oldValue) / interval * 3600
            return instant
        return None

    def onDisconnect(self, Connection):
        #LogMessage("onDisconnect called for connection '" + Connection.Name + "'.")
        if Connection.Name in self.httpServerConns:
            LogMessage("deleting connection '" + Connection.Name + "'.")
            del self.httpServerConns[Connection.Name]


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
        data.isResponse = True
    else:
        data.isResponse = False

    # Réussie (valeur 0), Erreur (valeur 1)
    if (int.from_bytes(Data[37:38], byteorder='little',signed=False) & 0x80 == 0x80):
        data.isError = True
    else:
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
    buffer += int(header.idD2L).to_bytes(8, byteorder="little", signed=False)        #4(8)  : ID D2L
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

def CreateImagesIfNeeded():
    if ("D2LModuleElecCurrent" not in Images):
        LogMessage("Creating image D2LModuleElecCurrent")
        Domoticz.Image('D2L-elec_current.zip').Create()
    if ("D2LModuleElecLoad" not in Images):
        LogMessage("Creating image D2LModuleElecLoad")
        Domoticz.Image('D2L-elec_load.zip').Create()
    if ("D2LModuleElecMeter" not in Images):
        LogMessage("Creating image D2LModuleElecMeter")
        Domoticz.Image('D2L-elec_meter.zip').Create()
    if ("D2LModuleText" not in Images):
        LogMessage("Creating image D2LModuleText")
        Domoticz.Image('D2L-text.zip').Create()

# Name -> (Unit, Type, Subtype)
NameToUnit = {
  "Intensité": (1, 243, 23, "D2LModuleElecCurrent"),
  "Intensité (triphasé)":(2, 89, 1, "D2LModuleElecCurrent"),
  "Charge Electrique":(3, 243, 6, "D2LModuleElecLoad"),
  "HP/HC":(4, 250, 1, "D2LModuleElecMeter"),
  "Total":(5, 243, 29, "D2LModuleElecMeter"),
}

def CreateDeviceIfNeeded(Name):
    if not Name in NameToUnit:
        Domoticz.Error("Device name '" + Name + "' not defined")
        return None
    i = NameToUnit[Name][0]
    if DEBUG_FRAME_ENABLED:
        i += 100
    if i in Devices:
        dev = Devices[i]
    else:
        if DEBUG_FRAME_ENABLED:
            DName=Name+" - Debug"
        else:
            DName=Name
        dev = Domoticz.Device(Name=DName, Unit=i, Type=NameToUnit[Name][1], Subtype=NameToUnit[Name][2], Image=Images[NameToUnit[Name][3]].ID)
        dev.Create()
    return dev

def UpdateDevice(Name, nValue, sValue):
    dev = CreateDeviceIfNeeded(Name)
    if dev is None:
        return
    dev.Update(nValue, sValue)

def GetNumericValue(fieldsStr, data):
    fields = fieldsStr.split('+')
    val = 0
    for f in fields:
        if f in data:
            try:
                val += float(data[f])
            except ValueError:
                Domoticz.Error("Can't parse field " + f + " as numeric (value: " + data[f] + ")")
        else:
            Domoticz.Error("Field '" + f + "' does not exists in json")
    return val

def CreateAdditionalDeviceIfNeeded(Name, i, PhysicsUnit):
    if DEBUG_FRAME_ENABLED:
        i += 100
    if i in Devices:
        dev = Devices[i]
    else:
        if DEBUG_FRAME_ENABLED:
            DName=Name+" - Debug"
        else:
            DName=Name
        if PhysicsUnit == "TEXT":
            dev = Domoticz.Device(Name=DName, Unit=i, TypeName="Text", Image=Images["D2LModuleText"].ID)
        elif PhysicsUnit == "kWh":
            dev = Domoticz.Device(Name=DName, Unit=i, TypeName="kWh", Image=Images["D2LModuleElecMeter"].ID)
        else:
            dev = Domoticz.Device(Name=DName, Unit=i, TypeName="Custom", Options={'Custom':'1;' + PhysicsUnit}, Image=Images["D2LModuleElecMeter"].ID)
        dev.Create()
    return dev

def UpdateAdditionalDevices(data):
    global adLastValues
    #TODO: prétraiter le paramètre additional field (Mode5) histoire de pas le refaire a chaque message...
    fields = Parameters["Mode5"].split(';')
    i=0
    for fieldsAndUnit in fields:
        if fieldsAndUnit == "":
            continue
        temp = fieldsAndUnit.split('@')
        if len(temp) != 2:
            Domoticz.Error("Error parsing Additional Fields " + fieldsAndUnit+". Format is 'FieldName@Unit'")
            continue
        field = temp[0]
        unit = temp[1]
        if unit == "TEXT":
            if not field in data:
                Domoticz.Error("Field " + field + " does not exists in json")
                continue
        dev = CreateAdditionalDeviceIfNeeded(field, 20 + i, unit)
        if not dev.Unit in adLastValues:
            adLastValues[dev.Unit] = None
        if unit == "TEXT":
            dev.Update(0, data[field])
        elif unit == "kWh":
            val = GetNumericValue(field, data)
            if adLastValues[dev.Unit] != None:
                instant = _plugin.computeInstant(adLastValues[dev.Unit], val)
                dev.Update(0, str(round(instant))+";"+str(int(val)))
            adLastValues[dev.Unit] = val
        else:
            val = GetNumericValue(field, data)
            dev.Update(0, str(val), Options={'Custom':'1;' + unit})
        i += 1

global adLastValues
adLastValues = {}
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

# Generic helper functions
def ReadDebugFramesFile():
    frames = []
    path = os.path.join(Parameters["HomeFolder"], "frame_examples.txt")
    f = open(path,"r")
    for l in f.readlines():
        l = l.strip()
        if len(l) == 0 or l[0] == '#':
            continue
        index = l.find("##")
        if index < 0:
            frames.append([l, "", ""])
            continue
        index2 = l.find("##", index+2)
        if index2 < 0:
            frames.append([l[:index], l[index+2:], ""])
        else:
            frames.append([l[:index], l[index+2:index2], l[index2+2:]])
    return frames

def LogMessage(Message):
    if Parameters["Mode6"] == "None" or Parameters["Mode6"] == "Comm":
        Domoticz.Debug(Message)
    else:
        Domoticz.Log(Message)

def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            LogMessage( "'" + x + "':'" + str(Parameters[x]) + "'")
    LogMessage("Device count: " + str(len(Devices)))
    for x in Devices:
        LogMessage("Device:           " + str(x) + " - " + str(Devices[x]))
        LogMessage("Device ID:       '" + str(Devices[x].ID) + "'")
        LogMessage("Device Name:     '" + Devices[x].Name + "'")
        LogMessage("Device nValue:    " + str(Devices[x].nValue))
        LogMessage("Device sValue:   '" + Devices[x].sValue + "'")
        LogMessage("Device LastLevel: " + str(Devices[x].LastLevel))
    return

