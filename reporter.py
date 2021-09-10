
#  -------------- PCpactico UniAlert v0.8b - Mail Reporter (2017) ---------
#  Requeriments:
#      - Pillow Library 8.1.0 -> pip install Pillow==8.1.0
#      - 
#      - Python 3.8
#  Considerations:
#      - If you using Mail Parser with Gmail account, remenber give permissions to "less secure applications"
#        Please open this link with your account https://myaccount.google.com/lesssecureapps
#      - It's recommended to run "Mail Reporter" as cron job every day.
#  Firsts steps:
#      - Edit the filters.json with your preferences
#
#  How to run:
#      - python \path\mail_reporter
#
#  Thanks:
#       - Darrin Massena:  http://code.activestate.com/recipes/473810-send-an-html-email-with-embedded-image-and-plain-t/
#
# -----------------------------------------------------------------------

from datetime import datetime
# ------ Json
import json
#------- SQLite
import sqlite3
#------- Librerias para generar graficas
from io import BytesIO # libreria para Buffer de imagenes
from PIL import Image,  ImageDraw
#------ Libreria para enviar correo
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

#------- Otras
import os
import sys


# Retrieve Json Data
def get_json_data(json_file): 
    try:
        with open(json_file) as data_file:
            return json.load(data_file)
    except:
        print ("[!] ERROR: No existe: ", json_file)
        print ("    Ejecute primero mail-agent para generar el archivo Json y editelo posteriormente.")
        sys.exit(1)
            

# Connect to database
def sqlite3_connect(sqlite3_file):
    try:
        db_con = sqlite3.connect(sqlite3_file)
        db_cur = db_con.cursor()
        return db_con, db_cur
    except sqlite3.Error:
        print ("[!] ERROR: en acceso SQLite.")
        sys.exit(1)

def insert_filters_status(filter, last60d, lmdate, lsdate, status):
    try:
        db_con = sqlite3.connect('alertparser.db')
        db_cur = db_con.cursor()
    except sqlite3.Error:
        print ("Error: en acceso SQLite.")
        sys.exit(1)
    db_cur.execute("insert or replace into filter_results (filter, date_last_msg, date_last_sync, state, last60days) values('"+ filter +"','"+ lmdate +"','"+lsdate+"',"+ str(status) +",'"+last60d+"')")
    db_con.commit()
    db_con.close()

#  Returns a list with masks representing the last results.
def get_filters_status(js_filters, db_cur, date_today ):
    status_rows = []
    for filter in js_filters:
        daysmask = "0" * 30 # inicializa la mascara de resultados a todo 0
        dias_sin_estado = 0 # Inicializa el contador de dias sin estado a 0
        ultimo_msg_estado = '0' # Inicializa el estado del ultima msg a '0'
        db_cur.execute("SELECT result, datetime, id FROM filter_retention WHERE filter = '"+filter["filter"]+"'")
        rows = db_cur.fetchall()
        last_msg_date = datetime.strptime('01/01/1975 00:00:00', '%d/%m/%Y %H:%M:%S') # Asigna valor por defecto para comparar con fechas futuras
        for row in rows:
            d_row_date = datetime.strptime(row[1],'%d/%m/%Y %H:%M:%S')
            t_row_date = d_row_date.strftime('%d/%m/%Y')
            row_date = datetime.strptime(t_row_date,'%d/%m/%Y')
            if last_msg_date < row_date:
                last_msg_date = row_date

            days_dif = (date_today-row_date).days # Dias entre Hoy y row_date
            if days_dif < 30: # Si la diferencia entre dias es menor a 30 (dias de retencion) introduce el restultado en la mascara de resultados.
                 daysmask = daysmask[:days_dif] + str(row[0]) + daysmask[days_dif+1:]
        
        ultimo_estado = daysmask[0] # Recuperamos el estado mas reciente
        while (ultimo_msg_estado == '0' and dias_sin_estado < 30): # obtenemos los ultimos dias sin estado y el valor del ultimo estado
            dias_sin_estado = dias_sin_estado +1
            ultimo_msg_estado = daysmask[dias_sin_estado-1]
        
        # Dependiendo de del valor de dias_sin_estado y ultimo_msg_estado obtenemos filter_status(estado actual del filtro)
        if ultimo_estado == "1" or (ultimo_msg_estado == "1" and dias_sin_estado-1 <= filter["delay_days_error"]):
            filter_status = 1
        elif ultimo_estado == "3" or (ultimo_msg_estado == "3" and dias_sin_estado-1 <= filter["delay_days_error"]):
            filter_status = 3
        elif ultimo_estado == "2" or (ultimo_msg_estado == "2" and dias_sin_estado-1 <= filter["delay_days_error"]) or (dias_sin_estado-1 > filter["delay_days_error"] and dias_sin_estado-1 < 59):
            filter_status = 2
        elif dias_sin_estado-1 == 59:
            filter_status = 0
        else:
            filter_status = 3
        
        status_rows.append([filter["caption"], daysmask,d_row_date.strftime('%d/%m/%Y %H:%M:%S'), filter_status, filter["group"], filter["desc_text"] ])
    return status_rows

def get_body_representation(status_list, error_body):
    f_error = 0
    f_success = 0
    f_alert = 0
    html_body = "<div style=\"text-align: left;\"><table style=\"border-spacing: 0px;width:95%;padding:0px;\" align=center>"
    html_body += "<tr style=\"color:white;background-color:"+ ( "#8c2323" if error_body else "#028ae6") +";text-align: left;\"><th colspan=\"4\" align=center>"+ ( "ERRORES DETECTADOS" if error_body else "RESUMEN TODAS LAS TAREAS")  +"</tr>\n"
    html_body += "<tr style=\"color:white;background-color:"+ ( "#a32929" if error_body else "#0098ff") +";text-align: left;\"><th width=\"35%\" style=\"font-size:1vw\">TAREA "+ ( "FALLIDA" if error_body else "") +"</th><th width=\"25%\" style=\"font-size:1vw\">FECHA</th><th width=\"15%\" style=\"font-size:1vw\">ESTADO</th><th width=\"25%\" style=\"font-size:1vw\">ULTIMOS 30 DIAS</th></tr>\n"

    img_id=1

    barras_buff = [BytesIO() for i in range(len(status_list))] #Inicializa el buffer de imagenes (barras representativas de resultados)

    group_last = ""  
    for row in sorted(status_list, key=lambda grupo: grupo[4], reverse=False): # Itera entre las lineas ordenado por "group"
        
        if group_last != row[4]: # Si el grupo es diferente, entonces añade cabecera del grupo
            html_body = html_body +"<tr style=\"color:black;background-color:"+ ( "#b0a9a9" if error_body else "#a5d8ff") +";text-align: left;font-size:1vw;\"><td colspan=4><b> "+ row[4] +"</b></td></tr>\n"


            group_last = row[4]
        
        WeekDay = datetime.today().isoweekday()
        barra = Image.new('RGB', (30*8,15)) #inicializa imagen
        lienzo = ImageDraw.Draw(barra) #inicializa lienzo de imagen
        pos=0
        
        for i in row[1]:
            if i == "0":
                if (WeekDay<6):
                    lienzo.rectangle(((pos*8,0),((pos*8)+8,14)), fill="#f1f1f1", outline="#d1d1d1")
                else:
                    lienzo.rectangle(((pos*8,0),((pos*8)+8,14)), fill="#e1e1e1", outline="#d1d1d1")
            elif i == "1":
                if (WeekDay<6):
                    lienzo.rectangle(((pos*8,0),((pos*8)+8,14)), fill="#00bc09", outline="#d1d1d1")
                else:
                    lienzo.rectangle(((pos*8,0),((pos*8)+8,14)), fill="#00cc09", outline="#d1d1d1")
            elif i == "2":
                if (WeekDay<6):
                    lienzo.rectangle(((pos*8,0),((pos*8)+8,14)), fill="#ff0000", outline="#d1d1d1")
                else:
                    lienzo.rectangle(((pos*8,0),((pos*8)+8,14)), fill="#ff4444", outline="#d1d1d1")
            else:
                lienzo.rectangle(((pos*8,0),((pos*8)+8,14)), fill="black", outline="#d1d1d1")
            pos = pos +1
            WeekDay = WeekDay -1
            if ( WeekDay < 1): WeekDay = 7
        
        barra.save(barras_buff[img_id-1], format="PNG") # Guarda la imagen generada en barras_buff en formato PNG
        
        if img_id%2 == 0: #Alterna el color de la linea (par = blanco / impar = #f1f1f1 )
            html_body = html_body + "<tr>"
        else:
            html_body = html_body + "<tr style=\"background-color:#f1f1f1;\">"

        html_body = html_body + "<td style=\"font-size:1.2vw\"><span title=\"" + row[5] + "\">" + row[0] + "</span></td>" # Nombre de filtro

        if row[2] == "1975-01-01 00:00:00":  # fecha ultimo msg
            html_body = html_body + "<td style=\"font-size:1.2vw\">----</td>"
        else:
            html_body = html_body + "<td style=\"font-size:1.2vw\">"+ row[2] +"</td>"

        if row[3] == 0:  # Estado
            html_body = html_body + "<td style=\"font-size:1.2vw\">----</td>"
        elif row[3] == 1:
            html_body = html_body + "<td style=\"font-size:1.2vw\">VALIDO</td>"
            f_success += 1
            
        elif row[3] == 2:
            html_body = html_body + "<td style=\"font-size:1.2vw\">ERROR</td>"
            f_error += 1
            
        else:
            html_body = html_body + "<td style=\"font-size:1.2vw\">ALERTA</td>"
            f_alert += 1
            
        if error_body:
            html_body = html_body + "<td width=\"1%\"><img alt=\"Embedded Image\" src=\"cid:image_e"+ str(img_id) + "\" width='100%'/></td></tr>\n"
        else:
            html_body = html_body + "<td width=\"1%\"><img alt=\"Embedded Image\" src=\"cid:image"+ str(img_id) + "\" width='100%'/></td></tr>\n"

        img_id = img_id +1
    html_body = html_body + "</table></div><br>"

    if error_body:
        return barras_buff, html_body
    else:
        return barras_buff, html_body, f_error, f_alert, f_success

def send_email_report(mail_config, html_body, bf_images, bf_images_err, f_error = 0, f_alert = 0, f_success = 0):
    msg = MIMEMultipart('multipart')
    msg['Subject'] = "=?utf-8?Q?=F0=9F=94=94?= RESUMEN DIARIO BACKUPS  [=?utf-8?Q?=E2=9D=8C?= " + str(f_error) + " =?utf-8?Q?=E2=9C=94?= "+ str(f_success) +"]"
    msg['From'] = mail_config["from"]
    msg['To'] = mail_config["to"]
    msg.preamble = 'This is a multi-part message in MIME format.'
    attach_1 = MIMEText(html_body, "html")
    msg.attach(attach_1)

    try:
        s = smtplib.SMTP(mail_config["smtp_server"] +':' + str(mail_config["smtp_port"]))
        s.ehlo()
        if mail_config["smtp_ssl"] == 1: s.starttls()
        s.login(mail_config["user"], mail_config["password"])
        for i, buff in enumerate(bf_images):
            img = MIMEImage(buff.getvalue())
            img.add_header('Content-ID', '<image'+ str(i+1)+'>')
            msg.attach(img)
        for i, buff in enumerate(bf_images_err):
            img = MIMEImage(buff.getvalue())
            img.add_header('Content-ID', '<image_e'+ str(i+1)+'>')
            msg.attach(img)
        s.sendmail(msg['From'], msg['To'], msg.as_string())
        s.quit()
    except Exception as e:
        print (str(e))
        sys.exit(1)


#-- Comprueba listado SQL
print ("\u001b[44;1m" + "### PCpactico UniAlert v0.5b - Mail Reporter (2017) - www.pcpractico.es ###" + "\u001b[0m")

Json_file = os.path.dirname(os.path.realpath(__file__)) + os.sep + 'filters.json'# Gets the path where python was run
SQLite_file = os.path.dirname(os.path.realpath(__file__)) + os.sep + 'alertparser.db'# Gets the path where python was run
today = datetime.strptime(datetime.now().strftime('%d/%m/%Y'),'%d/%m/%Y')

if len(sys.argv) != 1:
   for ss in sys.argv:
        if ss.lower() == "-h":
            print ("- How to use: python \path\mail_agent [-h][-r]")
            print ("     [-h] : Show this help and stop running")
            print ("     [-p] : Path to config and database files")
            print ("           -p:/opt/configfile/")
            sys.exit()
        if ss.lower()[:3] == "-p:":
            print ("- Path to config and database files: " + ss.lower()[3:] )
            if ss.lower()[-1] == os.sep:
                param_path = ss.lower()[3:-1]
            else: 
                param_path = ss.lower()[3:]

            if os.path.exists(param_path):
                Json_file = param_path + os.sep + 'filters.json'
                SQLite_file = param_path + os.sep + 'alertparser.db'
            else:
                print ("[!] Path does not exist or is incorrect.")
                sys.exit()   
            
            if not(os.path.exists(Json_file)):
                print ("[!] Config file does not exist.")
                sys.exit()   



print ("- Loading Json data file: " + Json_file)
json_data = get_json_data(Json_file)  # Retrieve Json data
lastsync = datetime.strptime(json_data["last_update"],'%d/%m/%Y %H:%M:%S')

if json_data["activated"]:
    print ("- Connecting to database: " + SQLite_file)
    db_con, db_cur = sqlite3_connect(SQLite_file)

    print ("- Generating result masks")
    a = get_filters_status(json_data["pcpfilters"], db_cur, today)
    db_con.close()

    f_err = []
    for item_r in a:
        if item_r[3] > 1:
            f_err.append(item_r)

    print ("- Generating images and Html report")

    img_buff, html_body, f_error, f_alert, f_success = get_body_representation(a, False)
    img_buff_err, html_body_err = get_body_representation(f_err, True)

    html_body = html_body_err + html_body


    print ("- Sending Email report")
    send_email_report(json_data["mail_config"], html_body, img_buff, img_buff_err, f_error, f_alert, f_success)
else:
    print ("[!] ALERT: system disabled, please edit filters.json config file and enable it.")

print ("- Work done")




