# Domoticz D2L Plugin
Domoticz Plugin For Eesmart D2L Module For Linky

This plugin allows to retrieve information from the french Linky electricity meter in Domoticz.

Ce plugin permet la remontée des informations TIC de Linky vers Domoticz via le module D2L de Eesmart, connecté localement au serveur Domoticz. Le plugin fonctionne en mode TIC  historique et standard pour des contrats Base et HP/HC. La gestion de la production d'énergie est possible en mode Standard (non testé).

## Installation
Requis : Testé uniquement sur Domoticz version 2020.2, Python 3 doit être installé.

Pour récupérer la version de développement :
* En ligne de commande aller dans le répertoire plugin de Domoticz (domoticz/plugins)
* Lancer la commande: ```git clone https://github.com/ultrasuperpingu/DomoticzD2LPlugin.git```
* Redémarrer le service Domoticz en lancant la commande ```sudo service domoticz restart```

Vous pouvez aussi simplement copier le fichier plugin.py dans le répertoire domoticz/plugins/{NomDeRepertoireDeNotreChoix} et redémarrer domoticz.

Pour récupérer une release, télécharger la version et décompresser l'archive dans le répertoire domoticz/plugins/{NomDeRepertoireDeNotreChoix} et redémarrer domoticz.

## Mise à Jour

Pour mettre à jour le plugin :

* En ligne de commande, aller dans le répertoire plugin de Domoticz (domoticz/plugins)
* Lancer la commande: ```git pull```
* Redémarrer le service Domoticz en lancant la commande ```sudo service domoticz restart```

Vous pouvez également mettre à jour le fichier plugin.py dans le répertoire domoticz/plugins/{NomDeRepertoireDeVotreChoix} et redémarrer domoticz.

## Configuration
| Field | Information|
| ----- | ---------- |
| Port  | Port IP à configurer dans le module (Valeur par défaut : 8008) . Quand vous configurez le module, c'est ce port que vous devez renseigner et pas le port de l'interface de Domoticz (généralement 8080). L'adresse IP à configurer dans le module est celle du serveur Domoticz. |
| App Key | La clef applicative correspondant à votre module nécessaire au déchiffrement des trames du module (32 caractères, nombre hexadécimal) |
| IV | (Lire i.v. et non 4) Le vecteur d'initialisation (Initialization Vector) AES correspondant à votre module nécessaire au déchiffrement des trames du module (32 caractères, nombre hexadécimal) |
| Standard Mode Config| Correspondance champs JSON->signification pour le mode standard. En mode standard, il semble que la valeur des champs varie d'un fournisseur à un autre. Il est donc plus simple de proposer de configurer la signification des champs. Il faut indiquer 4 champs séparés par des ; avec dans l'ordre, les compteurs suivants :<br/>Conso Heures Pleines;Conso Heures Creuses;Prod Heures Pleines;Prod Heures Creuses<br/><br/>Valeurs typiques :<br/><br/><ul><li>Avec production :</li><ul><li>EDF contrat BASE : "EASF01;;EAIT;</li><li>EDF contrat HP/HC : "EASF02;EASF01;EAIT;</li> <li>EDF contrat HC Week end : "EASF02;EASF01+EASF03;EAIT;</li></ul><li>Sans production : Laissez les 2 derniers champs vides</li></ul> |
| Additional Fields | Des champs du message json à ajouter en custom sensor. Les champs doivent être séparés par un ; et suffixé de @ suivi de l'unité du champ (si l'unité est TEXT, le champ sera de type "Texte", si l'unité est kWh, le champs sera traité comme un compteur Domoticz). Les sommes de champs sont gérées (il suffit de séparer les noms des champs par un +).<br/>Exemple: "ADIR1@A;HCHP+HCHC@kWh;ADIR1@TEXT" |
| Debug | All/Communication/None. Communication permet de ne loguer que les données envoyées par le module |

Dans la partie Matériel de Domoticz:

 * Chercher 'Eesmart D2L ERL Module'.
 * Renseigner les paramètres
 * Ajouter le matériel
 
Du coté du module, suivez la procédure de la documentation du module pour le faire pointer vers le serveur domoticz et vers le port que vous avez configuré dans le plugin.

## Utilisation
Dès que le plugin recevera les premières infos, il créera les équipements nécessaires (les termes en majuscules désignent les champs TIC (voir la spécification Enedis)) :
 * Intensité instantanée: Monophasé: une intensité (IINST), Triphasé: 3 intensités combinées en un dispositif (IINST1, IINST2, IINST3), Standard Monophasé : une intensité (IRMS1), Triphasé: 3 intensités combinées en un dispositif (IRMS1, IRMS2, IRMS3)</li>
 * Charge électrique : Pourcentage de charge du compteur (IINST/ISOUSC en monophasé ou max(IINST1,IINST2,IINST3)/ISOUSC en triphasé, standard: SINSTS/PCOUP)
 * En fonction du contrat :
   - Contrat Base : un compteur kWh (historique : BASE, standard: selon config)
   - Contrat HP/HC : un compteur de type P1 Smart Sensor regroupant les compteurs HP et HC (HCHP et HCHC, standard: selon config (gestion production possible))
   
Spécification Enedis : https://www.enedis.fr/sites/default/files/Enedis-NOI-CPT_54E.pdf

## Remonter un problème
Si le plugin ne fonctionne pas, activez le mode Debug dans les paramètres (Debug = All ou Communication). Si vous passez le module en Debug=All, l'ensemble des informations ne seront disponibles qu'après un redémarrage de Domoticz. Vous devriez alors avoir plus d'informations.
Si un messsage d'erreur apparait :
<ul>
 <li>soit c'est un message envoyé par le plugin, et il devrait vous donner la raison du problème</li>
 <li>soit il s'agit d'une erreur Python, dans ce cas, ouvrez un bug en renseignant ce message</li>
</ul>
Si vous ouvrez un bug, il serait préférable d'envoyer, s'il est visible dans les logs, la trame JSON envoyée par le module. Pensez à l'anonymiser en remplaçant notamment les chiffres du champ ADCO, et tous les champs que vous trouverez sensibles.

Si votre type de contrat n'est pas pris en charge par le plugin (TEMPO ou EJP), je ne garanti pas de faire le développement mais vous pouvez m'envoyer un exemple de trame JSON via l'ouverture d'un bug (idem, pensez à l'anonymiser).

Si aucun message n'apparait et que vous ne voyez pas les trames JSON envoyées par le module dans les logs, c'est que le module n'est pas convenablement configuré ou qu'un problème réseau l'empêche de communiquer avec le serveur Domoticz.

