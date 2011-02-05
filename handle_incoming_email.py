#!/usr/bin/env python

import logging, email
from datetime import datetime, timedelta, tzinfo
import time
import httplib
from random import random
from xml.dom.minidom import parseString
from google.appengine.ext import webapp 
from google.appengine.ext.webapp.mail_handlers import InboundMailHandler 
from google.appengine.ext.webapp import util
from google.appengine.api import mail
from google.appengine.ext import db


'''
TZInfo
'''

ZERO = timedelta(0)
HOUR = timedelta(hours=1)

# A UTC class.

class UTC(tzinfo):
    """UTC"""

    def utcoffset(self, dt):
        return ZERO

    def tzname(self, dt):
        return "UTC"

    def dst(self, dt):
        return ZERO

utc = UTC()

# A class building tzinfo objects for fixed-offset time zones.
# Note that FixedOffset(0, "UTC") is a different way to build a
# UTC tzinfo object.

class FixedOffset(tzinfo):
    """Fixed offset in minutes east from UTC."""

    def __init__(self, offset, name):
        self.__offset = timedelta(minutes = offset)
        self.__name = name

    def utcoffset(self, dt):
        return self.__offset

    def tzname(self, dt):
        return self.__name

    def dst(self, dt):
        return ZERO

# A class capturing the platform's idea of local time.

import time as _time

STDOFFSET = timedelta(seconds = -_time.timezone)
if _time.daylight:
    DSTOFFSET = timedelta(seconds = -_time.altzone)
else:
    DSTOFFSET = STDOFFSET

DSTDIFF = DSTOFFSET - STDOFFSET

class LocalTimezone(tzinfo):

    def utcoffset(self, dt):
        if self._isdst(dt):
            return DSTOFFSET
        else:
            return STDOFFSET

    def dst(self, dt):
        if self._isdst(dt):
            return DSTDIFF
        else:
            return ZERO

    def tzname(self, dt):
        return _time.tzname[self._isdst(dt)]

    def _isdst(self, dt):
        tt = (dt.year, dt.month, dt.day,
              dt.hour, dt.minute, dt.second,
              dt.weekday(), 0, -1)
        stamp = _time.mktime(tt)
        tt = _time.localtime(stamp)
        return tt.tm_isdst > 0

Local = LocalTimezone()


# A complete implementation of current DST rules for major US time zones.

def first_sunday_on_or_after(dt):
    days_to_go = 6 - dt.weekday()
    if days_to_go:
        dt += timedelta(days_to_go)
    return dt


# US DST Rules
#
# This is a simplified (i.e., wrong for a few cases) set of rules for US
# DST start and end times. For a complete and up-to-date set of DST rules
# and timezone definitions, visit the Olson Database (or try pytz):
# http://www.twinsun.com/tz/tz-link.htm
# http://sourceforge.net/projects/pytz/ (might not be up-to-date)
#
# In the US, since 2007, DST starts at 2am (standard time) on the second
# Sunday in March, which is the first Sunday on or after Mar 8.
DSTSTART_2007 = datetime(1, 3, 8, 2)
# and ends at 2am (DST time; 1am standard time) on the first Sunday of Nov.
DSTEND_2007 = datetime(1, 11, 1, 1)
# From 1987 to 2006, DST used to start at 2am (standard time) on the first
# Sunday in April and to end at 2am (DST time; 1am standard time) on the last
# Sunday of October, which is the first Sunday on or after Oct 25.
DSTSTART_1987_2006 = datetime(1, 4, 1, 2)
DSTEND_1987_2006 = datetime(1, 10, 25, 1)
# From 1967 to 1986, DST used to start at 2am (standard time) on the last
# Sunday in April (the one on or after April 24) and to end at 2am (DST time;
# 1am standard time) on the last Sunday of October, which is the first Sunday
# on or after Oct 25.
DSTSTART_1967_1986 = datetime(1, 4, 24, 2)
DSTEND_1967_1986 = DSTEND_1987_2006

class USTimeZone(tzinfo):

    def __init__(self, hours, reprname, stdname, dstname):
        self.stdoffset = timedelta(hours=hours)
        self.reprname = reprname
        self.stdname = stdname
        self.dstname = dstname

    def __repr__(self):
        return self.reprname

    def tzname(self, dt):
        if self.dst(dt):
            return self.dstname
        else:
            return self.stdname

    def utcoffset(self, dt):
        return self.stdoffset + self.dst(dt)

    def dst(self, dt):
        if dt is None or dt.tzinfo is None:
            # An exception may be sensible here, in one or both cases.
            # It depends on how you want to treat them.  The default
            # fromutc() implementation (called by the default astimezone()
            # implementation) passes a datetime with dt.tzinfo is self.
            return ZERO
        assert dt.tzinfo is self

        # Find start and end times for US DST. For years before 1967, return
        # ZERO for no DST.
        if 2006 < dt.year:
            dststart, dstend = DSTSTART_2007, DSTEND_2007
        elif 1986 < dt.year < 2007:
            dststart, dstend = DSTSTART_1987_2006, DSTEND_1987_2006
        elif 1966 < dt.year < 1987:
            dststart, dstend = DSTSTART_1967_1986, DSTEND_1967_1986
        else:
            return ZERO

        start = first_sunday_on_or_after(dststart.replace(year=dt.year))
        end = first_sunday_on_or_after(dstend.replace(year=dt.year))

        # Can't compare naive to aware objects, so strip the timezone from
        # dt first.
        if start <= dt.replace(tzinfo=None) < end:
            return HOUR
        else:
            return ZERO

Eastern  = USTimeZone(-5, "Eastern",  "EST", "EDT")
Central  = USTimeZone(-6, "Central",  "CST", "CDT")
Mountain = USTimeZone(-7, "Mountain", "MST", "MDT")
Pacific  = USTimeZone(-8, "Pacific",  "PST", "PDT")

'''
End of Tzinfo
'''

domain = "whenthesunrisesup.appspotmail.com"
city_ids = [2424766,
            2391279,
            2357536,
            2473224,
            2380358,
            2459115,
            2442047,
            2487956,
            2490383,
            2450022,
            2436704,
            2479651,
            2455920,
            2471217,
            2389876,
            2381475,
            2357112,
            2371464,
            2379574,
            2358820]

def fetch_city_temperature(city_id):
  conn = httplib.HTTPConnection("weather.yahooapis.com")
  conn.request("GET", "/forecastrss?w=" + str(city_id) + "&u=f")
  response = conn.getresponse()
  xml = response.read()
  dom = parseString(xml)
  location = dom.getElementsByTagName("yweather:location")[0]
  city = location.getAttribute("city")
  state = location.getAttribute("region")
  weather_condition = dom.getElementsByTagName("yweather:condition")[0]
  temperature = weather_condition.getAttribute("temp")
  conn.close()
  return (city, state, temperature)

def send_message(sender, subject, content, to):
  message = mail.EmailMessage()
  message.sender = sender
  message.subject = subject
  message.to = to
  message.body = content
  try:
    message.send()
  except mail.Error, e:
    logging.info("Error in sending email")

def str_to_tzinfo(tz_str):
  if tz_str == "ET":
    return Eastern
  if tz_str == "CT":
    return Central
  if tz_str == "MT":
    return Mountain
  if tz_str == "PT":
    return Pacific
  return Central
  
def str_to_datetime(raw_str):
  tz_str = raw_str.split(' ')[-1]
  tz_info = str_to_tzinfo(tz_str)
  t_struct = time.strptime(raw_str[:-3], '%b %d, %Y %I:%M %p')
  raw_time = datetime.fromtimestamp(time.mktime(t_struct))
  time_utcoffset = tz_info.utcoffset(raw_time)
  return raw_time - time_utcoffset

def datetime_to_str(raw_datetime):
  timezone_info = db.GqlQuery("SELECT * FROM TimezoneInfo ORDER BY update_time DESC").fetch(1)[0]
  t_delta = timedelta(hours=timezone_info.time_delta)
  local_datetime = raw_datetime + t_delta
  return local_datetime.strftime("%b %d, %Y %I:%M %p")

class TimezoneInfo(db.Model):
  update_time = db.DateTimeProperty(required=True)
  time_delta = db.IntegerProperty(required=True)

class Task(db.Model):
  task_type = db.StringProperty(required=True, choices=set(["personal", "academic", "business"]))
  valid_status = db.BooleanProperty(required=True)
  active_status = db.BooleanProperty(required=True)
  due_time = db.DateTimeProperty(required=True)
  task_content = db.TextProperty(required=True)
  insert_date = db.DateTimeProperty(required=True)
  update_date = db.DateTimeProperty(required=True)

class IncomingEmailHandler(InboundMailHandler):
  def sender_type(self, raw_sender):
    if raw_sender.find('<') == -1:
      sender = raw_sender
    else:
      sender = raw_sender.split('<')[1].split('>')[0]
    if sender == "root@localhost":
      return "personal"
    if sender == "root@localhost" or sender == "root@localhost":
      return "academic"
    if sender.split("@")[1] == "localhost":
      return "business"
    return 0
  
  def send_error(self, subject, content, to):
    send_message("error@" + domain, subject, content, to)
  
  def insert(self, sender_type, subject, context, to):
    try:
      current_datetime = datetime.utcnow()
      task_due_time = str_to_datetime(subject)
      entity = Task(task_type=sender_type,
                    valid_status=True,
                    active_status=True,
                    task_content=db.Text(context),
                    due_time=task_due_time,
                    insert_date=current_datetime,
                    update_date=current_datetime)
    
      entity.put()
      entity_key = str(entity.key())
      confirmation_sender = entity_key + "@" + domain
      confirmation_subject = "Confirmation of Adding New Task"
      confirmation_context = """Greetings,
New task of time [""" + subject + """] has been added!
Regards,
WTSRU"""
      send_message(confirmation_sender, confirmation_subject, confirmation_context, to)
    except:
      confirmation_subject = "Error in Adding New Task"
      confirmation_context = """Greetings,
Error occurs when trying to add new task of time [""" + subject + """]!
Regards,
WTSRU"""
      self.send_error(confirmation_subject, confirmation_context, to)
  
  def view_all(self, sender):
    tasks = db.GqlQuery("SELECT * FROM Task WHERE due_time > :1 ORDER BY due_time ASC", datetime.utcnow())
    content = "Greetings,\nHere is a list of all tasks coming by-\n\n"
    for task in tasks:
      content += datetime_to_str(task.due_time) + "\n"
      content += task.task_content
      content += "Active: "
      if task.active_status:
        content += "1"
      else:
        content += "0"
      content += " Valid: "
      if task.valid_status:
        content += "1"
      else:
        content += "0"
      content += "\n\n"
    content += "Take your time! Cheers!\nWTSRU"
    send_message("all@" + domain, "List of coming tasks", content, sender)
  
  def errrr(self, sender):
    random_id = int(random() * len(city_ids))
    city, state, temperature = fetch_city_temperature(city_ids[random_id])
    context = "Greetings,\n"
    context += "The temperature of " + city + ", " + state + " at the moment is " + temperature + "F. "
    context += "Oops, what's this? Want to get the temperature for another random city? Come on, shot me!\n"
    context += "Regards,\nWTSRU"
    self.send_error("You must be kidding me!", context, sender)
  
  def task_delete(self, task, sender):
    task.valid_status = False
    task.update_date = datetime.utcnow()
    task.put()
    entity_key = str(task.key())
    confirmation_sender = entity_key + "@" + domain
    confirmation_subject = "Confirmation of Updating Task"
    confirmation_context = """Greetings,
Task of [""" + entity_key + """] has been trashed!
Regards,
WTSRU"""
    send_message(confirmation_sender, confirmation_subject, confirmation_context, sender)
  
  def task_activate(self, task, sender):
    task.active_status = True
    task.update_date = datetime.utcnow()
    task.put()
    entity_key = str(task.key())
    confirmation_sender = entity_key + "@" + domain
    confirmation_subject = "Confirmation of Updating Task"
    confirmation_context = """Greetings,
Task of [""" + entity_key + """] has been activated!
Regards,
WTSRU"""
    send_message(confirmation_sender, confirmation_subject, confirmation_context, sender)
  
  def task_inactivate(self, task, sender):
    task.active_status = False
    task.update_date = datetime.utcnow()
    task.put()
    entity_key = str(task.key())
    confirmation_sender = entity_key + "@" + domain
    confirmation_subject = "Confirmation of Updating Task"
    confirmation_context = """Greetings,
Task of [""" + entity_key + """] has been inactivated!
Regards,
WTSRU"""
    send_message(confirmation_sender, confirmation_subject, confirmation_context, sender)
  
  def task_detail(self, task, sender):
    entity_key = str(task.key())
    confirmation_sender = entity_key + "@" + domain
    confirmation_subject = "Detail information of Task"
    content = "Greetings,\nHere is detail information of Task [" + entity_key + "]-\n\n"
    content += "Entity Key: " + entity_key + "\n"
    content += "Due time: " + datetime_to_str(task.due_time) + "\n"
    content += task.task_content + "\n"
    content += "Active: "
    if task.active_status:
      content += "1"
    else:
      content += "0"
    content += " Valid: "
    if task.valid_status:
      content += "1"
    else:
      content += "0"
    content += "\nInsert time: " + datetime_to_str(task.insert_date) + "\n"
    content += "Last update time: " + datetime_to_str(task.update_date)
    content += "\n\n"
    content += "Take your time! Cheers!\nWTSRU"
    send_message(confirmation_sender, confirmation_subject, content, sender)
  
  def task_update_date(self, task, new_date, sender):
    task.due_time = str_to_datetime(new_date)
    task.update_date = datetime.utcnow()
    task.put()
    entity_key = str(task.key())
    confirmation_sender = entity_key + "@" + domain
    confirmation_subject = "Confirmation of Updating Task"
    confirmation_context = """Greetings,
Due time of task [""" + entity_key + """] has been updated to [""" + new_date + """]!
Regards,
WTSRU"""
    send_message(confirmation_sender, confirmation_subject, confirmation_context, sender)
  
  def task_update_content(self, task, new_content, sender):
    task.task_content = db.Text(new_content)
    task.update_date = datetime.utcnow()
    task.put()
    entity_key = str(task.key())
    confirmation_sender = entity_key + "@" + domain
    confirmation_subject = "Confirmation of Updating Task"
    confirmation_context = """Greetings,
Content of task [""" + entity_key + """] has been updated to

""" + new_content + """

Regards,
WTSRU"""
    send_message(confirmation_sender, confirmation_subject, confirmation_context, sender)
  
  def task(self, content, task_id, sender):
    if task_id[0] == ' ':
      task_id = task_id[1:]
    task_key = db.Key(task_id)
    try:
      task = db.get(task_key)
      if content[:6] == "DELETE":
        self.task_delete(task, sender)
        return
      if content[:6] == "ACTIVE":
        self.task_activate(task, sender)
        return
      if content[:8] == "INACTIVE":
        self.task_inactivate(task, sender)
        return
      if content[:4] == "VIEW":
        self.task_detail(task, sender)
        return
      if content[:11] == "UPDATE DATE":
        self.task_update_date(task, content[12:], sender)
        return
      if content[:14] == "UPDATE CONTENT":
        self.task_update_content(task, content[15:], sender)
        return
      confirmation_subject = "Error in Updating Task"
      confirmation_context = """Greetings,
Error occurs when trying to update task! 
Sorry, but I cannot recognize your action to update the task. Your action is [""" + content + """], please double check!
Regards,
WTSRU"""
      self.send_error(confirmation_subject, confirmation_context, sender)
    except:
      confirmation_subject = "Error in Updating Task"
      confirmation_context = """Greetings,
Error occurs when trying to update task! 
Sorry, but I cannot find a task with id [""" + task_id + """], please double check.
Regards,
WTSRU"""
      self.send_error(confirmation_subject, confirmation_context, sender)
  
  def receive(self, mail_message):
    global domain
    if mail_message.to == "error@" + domain:
      self.errrr(mail_message.sender)
      return
    sender_type = self.sender_type(mail_message.sender)
    if sender_type:
      time_delta_int = int(mail_message.date[-5:]) / 100
      timezone_entity = TimezoneInfo(update_time=datetime.utcnow(),
                                     time_delta=time_delta_int)
      timezone_entity.put()
      to = mail_message.to
      subject = mail_message.subject
      content = mail_message.bodies('text/plain')
      for each_to in to:
        to_split = to.split('@')
        if to_split[1] == domain:
          for content_type, body in content:
            decoded_text = body.decode().splitlines(True)[0]
            action = to_split[0]
            if action == "new":
              self.insert(sender_type, subject, decoded_text, mail_message.sender)
              return
            if action == "all":
              self.view_all(mail_message.sender)
              return
            self.task(decoded_text, action, mail_message.sender)
    else:
      context = """Greetings,
Are you sure you are the guy with a family name that you don't know how to pronounce?
If you are quite sure, reply me.
Regards,
WTSRU"""
      self.send_error("Error in recognizing your identity", context, mail_message.sender)

class CronJobHandler(webapp.RequestHandler):
  def get(self):
    current_time = datetime.utcnow()
    ten_minute_interval = timedelta(0, 10 * 60)
    one_hour_interval = timedelta(0, 60 * 60)
    one_day_interval = timedelta(1)
    one_month_interval = timedelta(30)
    self.dispatch_task("10-Minute-Notification", current_time + ten_minute_interval)
    self.dispatch_task("1-Hour-Notification", current_time + one_hour_interval)
    self.dispatch_task("1-Day-Notification", current_time + one_day_interval)
    self.dispatch_task("1-Month-Notification", current_time + one_month_interval)
  
  def dispatch_task(self, pre, start_time):
    time_interval = timedelta(0, 306)
    end_time = start_time + time_interval
    tasks = db.GqlQuery("SELECT * FROM Task WHERE due_time > :1 AND due_time < :2 ORDER BY due_time ASC", start_time, end_time)
    for task in tasks:
      if task.valid_status and task.active_status:
        self.email_notification(pre, task)
  
  def email_notification(self, pre, task):
    entity_key = str(task.key())
    sender = entity_key + "@" + domain
    to = "Longyi Qi <root@localhost>"
    subject = "[WTSRU " + pre + "] " + datetime_to_str(task.due_time)
    content = """Greetings,
Here is a reminder for you-
Time:
""" + datetime_to_str(task.due_time) + """
Task:
""" + task.task_content + """
Regards,
WTSRU
"""
    send_message(sender, subject, content, to)
    

def main():
    application = webapp.WSGIApplication([IncomingEmailHandler.mapping(), ('/cron/send', CronJobHandler)], debug=True)
    
    util.run_wsgi_app(application)


if __name__ == '__main__':
    main()
