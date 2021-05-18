import logging
import pymysql

class LoggerHandlerToMysql(logging.Handler):
    def __init__(self):
        self.host = "127.0.0.1"
        self.admin = "root"
        self.password = "123456"
        self.port = 3306
        self.db = "honeypot"
        self.table = "HTTP"
        logging.Handler.__init__(self)


    def emit(self,record):
        db = pymysql.connect(host=self.host, port=self.port, user=self.admin,password=self.password,db=self.db)
        cursor = db.cursor()
        message = record.message
        message_format = message.split("---")
        sql = "INSERT INTO %s(TIME, IP, PORT, DATA_TYPE, MSG) VALUES ('%s', '%s', '%s', '%s', '%s' )"\
             % (self.table, record.asctime ,message_format[0],message_format[1],message_format[2],message_format[3])
        try:
            cursor.execute(sql)
            db.commit()
        except:
            # Rollback in case there is any error
            db.rollback()
        db.close()
