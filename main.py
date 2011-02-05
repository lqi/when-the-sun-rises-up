#!/usr/bin/env python

from google.appengine.ext import webapp
from google.appengine.ext.webapp import util

class MainHandler(webapp.RequestHandler):
    def get(self):
        self.response.out.write("""
        <html>
        <body>
        <h1>(Wake Me Up) When the Sun Rises Up</h1>
        <p>Greetings,</p>
        <p>As I am getting old (sorry if you were born before 1987, lol), so I developed this geek project as an email-based RESTful DSL to schedule my daily life, and notify me via email so that I can free some memory in my head and malloc other important things.</p>
        <p>Just in case I may even forget how to use this, (you know I won't, ) here is an introduction about how to wake me up.</p>
        <pre>
        Send email to new@whenthesunrisesup.appspotmail.com to insert a new task
        with subject of datetime
        and ONLY first line of the email body will be treated as the task content

        Also, modify tasks by replying the email address of the particular task with the following content
        DELETE to remove this task
        ACTIVE to activate (by default)
        INACTIVE to make it GFW
        VIEW to get the detail content
        UPDATE DATE plus new datetime
        UPDATE CONTENT plus new content

        Meanwhile, shot email to all@whenthesunrisesup.appspotmail.com to get a list of all tasks.

        You may only receive email from error@whenthesunrisesup.appspotmail.com and never want to reply it.
        
        The acceptable datetime format is '%b %d, %Y %I:%M %p ?T', for example, 'Jun 1, 2005 1:33 PM CT'. 
        If you use Mac OS X, have a look at the top right corner of your screen, that's it.
        BTW, only American Timezones (ET, CT, MT and PT) are supported for now.
        </pre>
        <p>If you try one of the email addresses above, you will... So, if you are interested in this, please feel free to contact me by <a href="http://www.longyiqi.com/contact/">longyiqi.com/contact</a>.</p>
        <p>Best regards,</p>
        <p><a href="http://www.longyiqi.com">L.Q.<a></p>
        <br />
        <p>P.S.<br />Thanks Google for the rocking <a href="http://code.google.com/appengine/"><img src="http://code.google.com/appengine/images/appengine-noborder-120x30.gif"
        alt="Powered by Google App Engine" /></a>.</p>
        """)

def main():
    application = webapp.WSGIApplication([('/', MainHandler)],
                                         debug=True)
    
    util.run_wsgi_app(application)


if __name__ == '__main__':
    main()
