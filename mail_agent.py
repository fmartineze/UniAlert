#  -------------- PCpactico UniAlert v0.9b - Mail Parser (2017) ---------
#  Requeriments:
#      - tzlocal library 2.1 -> pip install tzlocal==2.1
#      - Python 3.8
#  Considerations:
#      - If you using Mail Parser with Gmail account, remenber give permissions to "less secure applications"
#        Please open this link with your account https://myaccount.google.com/lesssecureapps
#      - It's recommended to run "Mail Parser" as cron job every 10 minuts
#  Firsts steps:
#      - Edit the filters.json with your preferences
#
# -----------------------------------------------------------------------
# Build DockerFile:  docker build -t unialert .
# -----------------------------------------------------------------------

#import smtplib
import imaplib
import email
from email.header import  decode_header
from email.utils import parsedate_tz, mktime_tz
from datetime import datetime, timedelta
from tzlocal import get_localzone
#import time
import json
import sqlite3
import sys
import os
from datetime import datetime
import base64

import gettext #Multilanguage lib

# Connect to database
def sqlite3_connect(sqlite3_file):
    try:
        db_con = sqlite3.connect(sqlite3_file)
        db_cur = db_con.cursor()
        return db_con, db_cur
    except sqlite3.Error as e:
        print("- "+ _("ERROR") +": "+ _("Can't connect to SQLite database."))
        sys.exit(1)

# Insert rows into database
def sqlite3_insert(filter, result, datetime, SQLite_file):
    db_con, db_cur = sqlite3_connect(SQLite_file)
    db_cur.execute("INSERT INTO filter_retention(filter, result, datetime) SELECT '"+ filter +"',"+ str(result) +",'"+ datetime +"' WHERE NOT EXISTS (SELECT filter FROM filter_retention  WHERE filter='"+filter+"' AND datetime='"+datetime+"');")
    db_con.commit()
    db_con.close

# Remove all rows from database
def sqlite3_delete_all(SQLite_file):
    db_con, db_cur = sqlite3_connect(SQLite_file)
    db_cur.execute("DELETE FROM filter_retention")
    db_con.commit()
    db_cur.execute("DELETE FROM filter_results")
    db_con.commit()
    db_con.close

# Remove rows that mach id_to_delte and filter_name
def sqlite3_delete(id_to_delete, filter_name, SQLite_file):
    db_con, db_cur = sqlite3_connect(SQLite_file)
    db_cur.execute("DELETE FROM filter_retention WHERE id ="+ str(id_to_delete))
    db_con.commit()
    db_cur.execute("DELETE FROM filter_results WHERE filter ='"+ filter_name +"'")
    db_con.commit()
    db_con.close

# Return mail data from imap server
def get_data_mail(filter_date_str, mail_config):
    try:
        print ("- " + _("Connecting to mail server") + " " + mail_config["mail_server"] + ":" + str(mail_config["port"]) + " (SSL)")
        if mail_config["ssl"] == 1:
            mail_con = imaplib.IMAP4_SSL(mail_config["mail_server"], mail_config["port"])           
        else:           
            mail_con = imaplib.IMAP4(mail_config["mail_server"], mail_config["port"])
        mail_con.login(mail_config["user"], mail_config["password"])
        mail_con.select('inbox')

        last_update_date = str(datetime.strptime(filter_date_str,'%d/%m/%Y %H:%M:%S').strftime("%d-%b-%Y")) # Change datetime string format.

        tmp, data = mail_con.search(None, '(SINCE '+ last_update_date +')')
        for n in data[0].split():
            tmp, data = mail_con.fetch(n, '(RFC822)' )
            yield data

        #return data
    except Exception as e:
        print ("- "+ _("ERROR") + ": " + str(e))
        sys.exit()

# Compare the mail data with the filters defineds into Json filter file.
def apply_filters(filtros, SQLite_file):     
    email.utils.formatdate(localtime=True)
    for response_part in get_data_mail(filtros["last_update"], filtros["mail_config"]):
        msg2 = email.message_from_bytes(response_part[0][1])

        try: ## Identifica si es Byte o STR.
            email_subject = ' '.join(t[0].decode(t[1] if t[1] else 'UTF-8') for t in decode_header(msg2['subject']))
        except AttributeError:
            email_subject = msg2['subject']
        
        if isinstance(msg2['from'], str):
            email_from = msg2['from']
        else:
            email_from = msg2['from'].encode('utf-8')   
                    
        email_date_utc = msg2['date']
        email_body = ''
        if msg2.is_multipart():

            #for payload in msg2.get_payload():               
            for payload in msg2.walk():               
                ctype = payload.get_content_type()
                cdispo = str(payload.get('Content-Disposition'))
                if ctype == 'text/plain' and 'attachment' not in cdispo:
                    body = str(payload.get_payload(decode=True))
                else:
                    body = payload.as_string()

                email_body = email_body + body                   
        else:
            email_body = msg2.get_payload(decode=True)
        

        timestamp = mktime_tz(parsedate_tz(email_date_utc))       
        email_date = datetime.fromtimestamp(timestamp, get_localzone())
        email_date_witout_tz = datetime.strptime(email_date.strftime("%d/%m/%Y %H:%M:%S"),'%d/%m/%Y %H:%M:%S')
        
        if (last_update_date <= email_date_witout_tz):
            
            #print ('* PARSING: '+ email_subject)

            for filter in filtros["pcpfilters"]:
                result = ""
                ftipo = filter["type"]
                fname = filter["filter"]
                ffrom =  filter["id_filter"]["from"]
                fsubject = filter["id_filter"]["subject"]
                fbody = filter["id_filter"]["body"]
                
                if (((ffrom in email_from) or (ffrom == "")) and ((fbody in str(email_body)) or (fbody == "")) and ((fsubject in email_subject) or (fsubject == ""))) and not(fbody == "" and fsubject == "" ):
                    
                    if ftipo == "search":
                        success_subject = filter["id_success"]["subject"]
                        success_body = filter["id_success"]["body"]
                        error_subject = filter["id_error"]["subject"]
                        error_body = filter["id_error"]["body"]

                        if (success_subject in email_subject and success_subject != "") or (success_body in str(email_body) and success_body != ""):
                            result = "OK"
                            sqlite3_insert(filter["filter"],1,str(email_date.strftime("%d/%m/%Y %H:%M:%S")), SQLite_file)

                        elif (error_subject in email_subject and success_subject != "") or (error_subject in str(email_body) and success_body != ""):
                            sqlite3_insert(filter["filter"],2,str(email_date.strftime("%d/%m/%Y %H:%M:%S")), SQLite_file)
                            result = "ERROR"
                        else:
                            sqlite3_insert(filter["filter"],3,str(email_date.strftime("%d/%m/%Y %H:%M:%S")), SQLite_file)
                            result = "ALERT"
                    elif ftipo == "cobian":
                        if ("[0]" in email_subject ):
                            sqlite3_insert(filter["filter"],1,str(email_date.strftime("%d/%m/%Y %H:%M:%S")), SQLite_file)
                            result = "OK"
                        else:
                            sqlite3_insert(filter["filter"],2,str(email_date.strftime("%d/%m/%Y %H:%M:%S")), SQLite_file)
                            result = "ERROR"
                    
                    print (' * ' + _('FOUND') + ': '+ str(email_date.strftime("%d/%m/%Y %H:%M:%S")) +' [' + fname +'] = ' + result)

# RetCheck if a filter exist into Json file
def exist_json_filter(filter_name, filters):
    s = False
    for i in filters:
        if i["filter"] == filter_name:
            s= True
    return s

# Clear old rows into database and inexistents filters
def clean_database(filter, SQLite_file):
    
    db_con, db_cur = sqlite3_connect(SQLite_file)
    
    try:      
        db_cur.execute("SELECT * FROM filter_retention")
    except:
        print ("[!] ALERT: Database file not found")
        print ("- Creating database file and schema")
        sql_str = """   PRAGMA foreign_keys=OFF;
                        BEGIN TRANSACTION;
                        CREATE TABLE IF NOT EXISTS "filter_retention" (
                            `ID`	INTEGER PRIMARY KEY AUTOINCREMENT,
                            `filter`	TEXT,
                            `result`	INTEGER DEFAULT 0,
                            `datetime`	TEXT
                        );
                        CREATE TABLE `filter_results` (
                            `filter`	TEXT,
                            `date_last_msg`	TEXT,
                            `date_last_sync`	TEXT,
                            `state`	INTEGER,
                            `last60days`	TEXT,
                            PRIMARY KEY(`filter`)
                        );
                        DELETE FROM sqlite_sequence;
                        INSERT INTO sqlite_sequence VALUES('filter_retention',28484);
                        COMMIT;"""
        db_cur.executescript(sql_str) #Crea estructura de la bbdd en caso de que no exista       
       
    rows = db_cur.fetchall()
    for row in rows:
       row_date = datetime.strptime(row[3], '%d/%m/%Y %H:%M:%S')
       # Check if has more than 60 days
       if row_date < (datetime.now() - timedelta(days=60)) :
           sqlite3_delete (row[0], row[1], SQLite_file)
       # Check if the filter exists
       if not exist_json_filter(row[1], filter["pcpfilters"]):
           sqlite3_delete (row[0], row[1], SQLite_file)
    db_con.close()

# Retrieve Json Data
def get_json_data(json_file): 
    try:
        with open(json_file) as data_file:
            return json.load(data_file)
    except:
        print ("[!] " + _("ALERT") +": " + _("Config file does not exist."))
        create_json_data(json_file)
        sys.exit(1)

# Create new Json date file
def create_json_data(json_file):
    print ("- Initializing configuration file: ", Json_file)
    json_template = {
        "activated" : "false",
        "last_update" : "01/01/2000 00:00:00",
        "language" : "en_US",
        "mail_config" : {
            "from"        : "mailfrom@domain.com",
            "to"          : "mailto@domain.com",
            "mail_server" : "imap.mailserver.com",
            "port"        : 993,
            "ssl"         : 1,
            "smtp_server" : "smtp.mailserver.com",
            "smtp_port"   :  587,
            "smtp_ssl"    : 1,
            "user"        : "mailuser",
            "password"    : "mypassword"
        },
        "pcpfilters" : [
            {
                "caption"           : "text to be displayed",
                "filter"            : "filter identification text, must be unique",
                "desc_text"         : "filter description text",
                "group"             : "filter grouping identification text",
                "days_retention"    : 30,
                "delay_days_error"  : 3,
                "type"              : "search",
                "id_filter"         : {
                    "from"     : "mailfrom@domain.com",
                    "body"     : "string to find on the body",
                    "subject"  : "string to find on the subject"
                },
                "id_success"        : {
                    "body"     : "string to find on the body",
                    "subject"  : "string to find on the subject"
                },
                "id_error"        : {
                    "body"     : "string to find on the body",
                    "subject"  : "string to find on the subject"
                }
            }
        ]

    }
    with open(Json_file, 'w') as data_file:
        json.dump(json_template, data_file, indent=4,sort_keys=True)
    print ("- Job done. Please edit the filters.json file and try again")


# ------------------------------------------------------
print ("\u001b[44;1m" + "### PCpactico UniAlert - Mail Agent (2017) - www.pcpractico.es ###" + "\u001b[0m")

now = datetime.now()
print("- " + now.strftime("%d/%m/%Y %H:%M:%S") )
Json_file   = os.path.dirname(os.path.realpath(__file__)) + os.sep + 'filters.json' # Gets the path where python was run
SQLite_file = os.path.dirname(os.path.realpath(__file__)) + os.sep + 'alertparser.db' # Gets the path where python was run
locale_path = os.path.dirname(os.path.realpath(__file__)) + os.sep + 'locale' # Get the locale files path for multilanguage lib

# --- Procesar argumentos ----- 
if len(sys.argv) != 1:
    # Opción: Mostrar Ayuda
    if "-h" in sys.argv:
        print ("- How to use: python \path\mail_agent [-option]")
        print ("     [-h]     : Show this help and stop running")
        print ("     [-j]     : Create sample Json configuration file")
        print ("     [-p]     : Path to config and database files")
        print ("               -p:/opt/configfile/")        
        print ("     [-r]     : Remove all data from the database and stop running")
        print ("     [-y]     : Always say yes to any prompt")
        sys.exit()
    #Opción: indicar ruta archivos de bbdd y configuración
    if any("-p" in x for x in sys.argv):
        pos =  [i for i, s in enumerate(sys.argv) if '-p' in s][0]
        ss = sys.argv[pos]
        #sys.exit()
        print ("- Path to config and database files: " + ss.lower()[3:] )

        if ss.lower()[-1] == os.sep:
            param_path = ss.lower()[3:-1]
        else: 
            param_path = ss.lower()[3:]

        if os.path.exists(param_path):
            Json_file = param_path + os.sep + 'filters.json'
            SQLite_file = param_path + os.sep + 'alertparser.db'
        else:
            print ("[!] : Path does not exist or is incorrect.")
            sys.exit()   
        if (  (not(os.path.exists(Json_file)) and (not("-j" in sys.argv) ))  ):
            print ("[!] ALERT: Config file does not exist.")
            create_json_data(Json_file)
            sys.exit() 

    #Opción: Vaciar base de datos
    if "-r" in sys.argv:
        print ("[!] ALERT: All data from the database will be deleted.")
        while True:
            if ("-y" in sys.argv) :
                print ("    Are you sure? [Y/N]: YES")
                sw1 = "y"
            else:
                sw1 = input ("    Are you sure? [Y/N]: ")

            if (sw1.lower() == "y"):
                print ("- Removing all data from the database")
                sqlite3_delete_all(SQLite_file)
                print("- Job done.")
                break
            elif (sw1.lower() == "n"):
                print("- Job canceled.")
                break
        sys.exit()
    
    #Opción: Crear archivo configuración Json
    if "-j" in sys.argv:
        print ("[!] ALERT: This will initialize the configuration file. If you already have a configuration file, this process will remove all of its content.")
        if ("-y" in sys.argv) :
            print ("    Are you sure? [Y/N]: YES")
            sw1 = "y"
        else:
            sw1 = input ("    Are you sure? [Y/N]: ")

        if (sw1.lower() == "y"):
            create_json_data(Json_file)
        else:
            print("- Job canceled.")

        sys.exit()

# ------- 

Json_data = get_json_data(Json_file)  # Retrieve Json data

# --- Carga el archivo de idioma correspondiente
select_lang = [Json_data["language"]]
langs = gettext.translation('mail_agent', 
                            locale_path, 
                            languages=select_lang, 
                            fallback=True,)
_ = langs.gettext

print ("- "+ _("Json configuration file loaded")+": " + Json_file)


if Json_data["activated"]:
    if Json_data["last_update"] == "":  # Get Last Update value from Json data file or get now if not exist
        Json_data["last_update"] = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    else:
        last_update_date = datetime.strptime(Json_data["last_update"],'%d/%m/%Y %H:%M:%S')

    print ("- " + _("Removing junk data"))
    clean_database(Json_data, SQLite_file)

    print ("- " + _("Applying filters"))
    apply_filters(Json_data, SQLite_file)

    #---- Modificar Json
    Json_data["last_update"] = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    sorted_json = Json_data
    sorted_json["pcpfilters"] = sorted(Json_data["pcpfilters"], key=lambda x : x['filter'], reverse=False)
    with open(Json_file, 'w') as data_file:
        json.dump(sorted_json, data_file, indent=4,sort_keys=True)

else:
    print ("[!] " + _("ALERT") +": "+ _("system disabled, please edit filters.json config file and enable it."))

print ("- "+ _("Work done"))

 
