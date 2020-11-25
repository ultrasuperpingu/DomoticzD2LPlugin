# Domoticz D2L Plugin
Domoticz Plugin For Eesmart D2L Module For Linky

This plugin allow to get information from the french electricity meter Linky in Domoticz.

Ce plugin permet la remontée des informations TIC de Linky vers Domoticz via le module D2L de Eesmart. Pour le moment, le module ne fonctionne qu'en mode historique pour des contrats Base et HP/HC.

## Installation
Requis : Testé uniquement sur Domoticz version 2020.2

* En ligne de commande aller dans le répertoire plugin de Domoticz (domoticz/plugins)
* Lancer la commande: ```git clone https://github.com/ultrasuperpingu/DomoticzD2LPlugin.git```
* Redémarrer le service Domoticz en lancant la commande ```sudo service domoticz restart```

## Mise à Jour

Pour mettre à jour le plugin :

* En ligne de commande aller dans le répertoire plugin de Domoticz (domoticz/plugins)
* Lancer la commande: ```git pull```
* Redémarrer le service Domoticz en lancant la commande ```sudo service domoticz restart```

## Configuration

| Field | Information|
| ----- | ---------- |
| Port  | Le port à utiliser |
| App Key | La clef applicative correspondant à votre module nécessaire au déchiffrement des trames du module |
| IV | Le vecteur d'initialiation AES correspondant à votre module nécessaire au déchiffrement des trames du module |
| Debug | All/Communication/None. Communication permet de ne loguer que les données envoyées par le module |

Dans la partie Matériel de Domoticz:

 * Chercher 'Eesmart D2L ERL Module'.
 * Renseigner les paramètres
 * Ajouter le matériel
 
Les champs App Key, IV et Port ne peuvent être modifié dynamiquement (en sélectionnant le matériel et en faisant Modifier). Pour prendre en compte la modification, vous devez redémarrer Domoticz (```sudo service domoticz restart```).

Du coté du module, suivez la procédure de la documentation du module pour le faire pointer vers le serveur domoticz et vers le port que vous avez configuré dans le plugin.

Dès que le plugin recevera les premières infos, il créera les équipements nécessaires :
 * Intensité instantanée
 * Charge électrique
 * En fonction du contrat :
   - un unique compteur kWh si contrat BASE
   - 3 compteurs kWh HP/HC/Total (seront probablement supprimés dans les prochaines versions) + 1 compteur de type P1 Smart Sensor si contrat HC

