import json
import os
import copy
import uuid
from collections import namedtuple, OrderedDict
import tornado.escape
import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web
from tornado.options import define, options

import traceback
from sqlalchemy import *
from concurrent.futures import ProcessPoolExecutor
import pickle
import pandas as pd 
import numpy as np
import requests
from astroquery.simbad import Simbad
import astropy.units as u
import pdb

from .pandexo import wrapper
from .utils.plotters import create_component_jwst, create_component_hst
from .logs import jwst_log, hst_log
from .exomast import get_target_data

#grab all planets for folks 
#all_planets =  pd.read_csv('https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query=select+pl_name+from+PSCompPars&format=csv')
#all_planets = sorted(all_planets['pl_name'].values)

# define location of temp files
__TEMP__ = os.environ.get("PANDEXO_TEMP", os.path.join(os.path.dirname(__file__), "temp"))

#define location of fort grids
try:
    __FORT__ = os.environ.get('FORTGRID_DIR')
    db_fort = create_engine('sqlite:///'+__FORT__)
except: 
    print('FORTNEY DATABASE NOT INSTALLED')

#add Simbad query info 
Simbad.add_votable_fields('flux(H)')
Simbad.add_votable_fields('flux(J)')

define("port", default=1111, help="run on the given port", type=int)
define("debug", default=False, help="automatically detect code changes in development")
define("workers", default=4, help="maximum number of simultaneous async tasks")

# Define a simple named tuple to keep track for submitted calculations
CalculationTask = namedtuple('CalculationTask', ['id', 'name', 'task',
                                                 'cookie', 'count', 'form_data'])

def getStarName(planet_name):
    """
    Given a string with a (supposed) planet name, this function returns the star name. For example:

    - If `planet_name` is 'HATS-5b' this returns 'HATS-5'.
    - If `planet_name` is 'Kepler-12Ab' this returns 'Kepler-12A'.
    
    It also handles the corner case in which `planet_name` is *not* a planet name, but a star name itself, e.g.:

    - If `planet_name` is 'HAT-P-1' it returns 'HAT-P-1'.
    - If `planet_name` is 'HAT-P-1  ' it returns 'HAT-P-1'.
    """

    star_name = planet_name.strip()

    # Check if last character is a letter:
    if str.isalpha(star_name[-1]):
        if star_name[-1] == star_name[-1].lower():
            star_name = star_name[:-1]
            
    # Return trimmed string:
    return star_name.strip()

class Application(tornado.web.Application):
    """Gobal settings of the server
    This defines the global settings of the server. This parses out the
    handlers, and includes settings for if ever we want to tie this to a
    database.
    """
    def __init__(self):
        handlers = [
            (r"/", HomeHandler),
            (r"/about", AboutHandler),
            (r"/dashboard", DashboardHandler),
            (r"/dashboardhst", DashboardHSTHandler),
            (r"/tables", TablesHandler),
            (r"/helpfulplots", HelpfulPlotsHandler),
            (r"/calculation/new", CalculationNewHandler),
            (r"/calculation/new/([^/]+)", CalculationNewHandler),
            (r"/calculation/newHST", CalculationNewHSTHandler),
            (r"/calculation/newHST/([^/]+)", CalculationNewHSTHandler),
            (r"/resolve", ResolveHandler),
            (r"/calculation/status/([^/]+)", CalculationStatusHandler),
            (r"/calculation/statushst/([^/]+)", CalculationStatusHSTHandler),
            (r"/calculation/view/([^/]+)", CalculationViewHandler),
            (r"/calculation/viewhst/([^/]+)", CalculationViewHSTHandler),
            (r"/calculation/download/([^/]+)", CalculationDownloadHandler),
            (r"/calculation/downloadtext/([^/]+)", CalculationDownloadTextHandler),
            (r"/calculation/downloadpandin/([^/]+)", CalculationDownloadPandInHandler)
        ]
        settings = dict(
            blog_title="Pandexo",
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            xsrf_cookies=True,
            cookie_secret="__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE_HERE__",
            debug=True,
        )
        super(Application, self).__init__(handlers, **settings)


class BaseHandler(tornado.web.RequestHandler):
    """
    Logic to handle user information and database access might go here.
    """
    executor = ProcessPoolExecutor(max_workers=16)
    buffer = OrderedDict()

    def _get_task_response(self, id):
        """
        Simple function to grab a calculation that's stored in the buffer,
        and return a dictionary/json-like response to the front-end.
        """
        calc_task = self.buffer.get(id)
        task = calc_task.task

        response = {'id': id,
                    'name': calc_task.name,
                    'count': calc_task.count}

        if task.running():
            response['state'] = 'running'
            response['code'] = 202
        elif task.done():
            response['state'] = 'finished'
        elif task.cancelled():
            response['state'] = 'cancelled'
        else:
            response['state'] = 'pending'

        response['html'] = tornado.escape.to_basestring(
            self.render_string("calc_row.html", response=response))
        return response

 
    def _get_task_response_hst(self, id):
        """
        Simple function to grab a calculation that's stored in the buffer,
        and return a dictionary/json-like response to the front-end.
        """
        calc_task = self.buffer.get(id)
        task = calc_task.task

        response = {'id': id,
                    'name': calc_task.name,
                    'count': calc_task.count}

        if task.running():
            response['state'] = 'running'
            response['code'] = 202
        elif task.done():
            response['state'] = 'finished'
        elif task.cancelled():
            response['state'] = 'cancelled'
        else:
            response['state'] = 'pending'

        response['html'] = tornado.escape.to_basestring(
            self.render_string("calc_rowhst.html", response=response))

        return response
        
    def write_error(self, status_code, **kwargs):
        """
        This renders a customized error page
        """
        reason = self._reason
        error_info = ''
        trace_print = ''
        if 'exc_info' in kwargs:
            error_info = kwargs['exc_info']
            try:
                trace_print = traceback.format_exception(*error_info)
                trace_print = "\n".join(map(str,trace_print))
            except:
                pass
        self.render('errors.html',page=None, status_code=status_code, reason=reason, error_log=trace_print)


    def _get_task_result(self, id):
        """
        This method grabs only the result returned from the python `Future`
        object. This contains the stuff that Pandeia returns.
        """
        calc_task = self.buffer.get(id)
        task = calc_task.task
        return task.result()

    def _add_task(self, id, name, task, form_data=None):
        """
        This creates the task and adds it to the buffer.
        """
        self.buffer[id] = CalculationTask(id=id, name=name, task=task,
                                          count=len(self.buffer)+1,
                                          cookie=self.get_cookie("pandexo_user"),
                                          form_data=form_data)

        # Only allow 100 tasks **globally**. This will delete old tasks first.
        if len(self.buffer) > 100:
            self.buffer.popitem(last=False)

class HomeHandler(BaseHandler):
    def get(self):
        """
        This sets an **unsecured** cookie. If user accounts gets
        implemented, this must be changed to a secure cookie.
        """
        if not self.get_cookie("pandexo_user"):
            self.set_cookie("pandexo_user", str(uuid.uuid4()))

        self.render("home.html")
        
class AboutHandler(BaseHandler):
    def get(self):
        """
        Render about PandExo Page
        """
        self.render("about.html")

class TablesHandler(BaseHandler):
    def get(self):
        """
        Render tables with confirmed candidates
        """
        self.render("tables.html")

class HelpfulPlotsHandler(BaseHandler):
    def get(self):
        """
        Renders helpful bokeh plots
        """
        self.render("helpfulplots.html")


class DashboardHandler(BaseHandler):
    """
    Request handler for the dashboard page. This will retrieve and render
    the html template, along with the list of current task objects.
    """
    def get(self):
        task_responses = [self._get_task_response(id) for id, nt in
                          list(self.buffer.items())
                          if ((nt.cookie == self.get_cookie("pandexo_user"))
                          & (id[len(id)-1]=='e'))]
        
        self.render("dashboard.html", calculations=task_responses[::-1])


class DashboardHSTHandler(BaseHandler):
    """
    Request handler for the dashboard page. This will retrieve and render
    the html template, along with the list of current task objects.
    """
    def get(self):
        task_responses = [self._get_task_response_hst(id) for id, nt in
                          list(self.buffer.items())
                          if ((nt.cookie == self.get_cookie("pandexo_user"))
                          & (id[len(id)-1]=='h'))]
        
        self.render("dashboardhst.html", calculations=task_responses[::-1])


        
class CalculationNewHandler(BaseHandler):
    """
    This request handler deals with processing the form data and submitting
    a new calculation task to the parallelized workers.
    """
    def get(self, id=None):
        try: 
            header= pd.read_sql_table('header',db_fort)
        except:
            header = pd.DataFrame({
            'temp': ['NO GRID DB FOUND'],
            'ray' : ['NO GRID DB FOUND'],
            'flat':['NO GRID DB FOUND']})

        with open(os.path.join(os.path.dirname(__file__), "reference",
                               "exo_input.json")) as data_file:
            exodata = json.load(data_file)

        form_data = None
        if id is not None:            
            form_data = self.buffer[id].form_data

        all_planets =  pd.read_csv('https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query=select+pl_name+from+PSCompPars&format=csv')
        all_planets = sorted(all_planets['pl_name'].values)
        unique_temps = sorted(header.temp.unique())
        self.render("new.html", id=id,
                                 temp=list(map(str, unique_temps)),
                                 planets=all_planets,
                                 data=exodata, data_json=json.dumps(form_data))

    
    def post(self):
        """
        The post method contains the returned data from the form data (
        accessed by using `self.get_argument(...)` for specific arguments,
        or `self.request.body` to grab the entire returned object.
        """
        
        #print(self.request.body)
        
        form_data = {}
        for key in self.request.arguments:
            form_data[key] = self.get_argument(key)

        id = str(uuid.uuid4())+'e'
       
        with open(os.path.join(os.path.dirname(__file__), "reference",
                        "exo_input.json")) as data_file:

            exodata = json.load(data_file)
            exodata["telescope"] = 'jwst'
            exodata["calculation"] = 'fml'

            #star

            exodata["star"]["temp"] = float(self.get_argument("temp"))
            exodata["star"]["logg"] = float(self.get_argument("logg"))
            exodata["star"]["metal"] = float(self.get_argument("metal"))  
            exodata["star"]["mag"] = float(self.get_argument("mag"))
            exodata["star"]["ref_wave"] = float(self.get_argument("ref_wave"))

            #optinoal star radius
            exodata["star"]["radius"] = float(self.get_argument("rstarc"))
            exodata["star"]["r_unit"] = str(self.get_argument("rstar_unitc"))

            #optional planet radius
            exodata["planet"]["radius"] = float(self.get_argument("refradc"))
            exodata["planet"]["r_unit"] = str(self.get_argument("r_unitc")) 

            #transit duration
            # for phase curves user doesn't necessarily have to input a transit duration
            try:
                exodata["planet"]["transit_duration"] = float(self.get_argument("transit_duration"))
                exodata["planet"]["td_unit"] = str(self.get_argument("td_unit"))
            except:
                # but if they don't.. make sure that the planet units are in seconds...
                if self.get_argument("planwunits") == 'sec':
                    exodata["planet"]["transit_duration"] = 0.0
                else: 
                    raise Exception("Need transit duraiton or input phase curve file")

            # stellar model
            exodata["star"]["type"] = self.get_argument("stellarModel")

            if exodata["star"]["type"] == "user":
                # process star file
                fileinfo_star = self.request.files['starFile'][0]
                fname_star = fileinfo_star['filename']
                extn_star = os.path.splitext(fname_star)[1]
                cname_star = id+'star' + extn_star
                fh_star = open(os.path.join(__TEMP__, cname_star), 'wb')
                fh_star.write(fileinfo_star['body'])
                fh_star.close()

                exodata["star"]["starpath"] = os.path.join(__TEMP__, cname_star)
                exodata["star"]["f_unit"] = self.get_argument("starfunits")
                exodata["star"]["w_unit"] = self.get_argument("starwunits")


            # planet model
            exodata["planet"]["type"] = self.get_argument("planetModel")
            if exodata["planet"]["type"] == "user":
                # process planet file
                fileinfo_plan = self.request.files['planFile'][0]
                fname_plan = fileinfo_plan['filename']
                extn_plan = os.path.splitext(fname_plan)[1]
                cname_plan = id+'planet' + extn_plan
                fh_plan = open(os.path.join(__TEMP__, cname_plan), 'wb')
                fh_plan.write(fileinfo_plan['body'])
                fh_plan.close()

                exodata["planet"]["exopath"] = os.path.join(__TEMP__, cname_plan)
                exodata["planet"]["w_unit"] = self.get_argument("planwunits")
                exodata["planet"]["f_unit"] = self.get_argument("planfunits")
            elif exodata["planet"]["type"] == "constant":                               
                if self.get_argument("constant_unit") == 'fp/f*':
                    exodata["planet"]["temp"] = float(self.get_argument("ptempc"))
                    exodata["planet"]["f_unit"] = 'fp/f*'
                elif self.get_argument("constant_unit") == 'rp^2/r*^2':
                    exodata["planet"]["f_unit"] = 'rp^2/r*^2'
            elif exodata["planet"]["type"] == "grid":
                exodata["planet"]["temp"] = float(self.get_argument("ptempg"))
                exodata["planet"]["chem"] = str(self.get_argument("pchem"))
                exodata["planet"]["cloud"] = self.get_argument("cloud") 
                exodata["planet"]["mass"] = float(self.get_argument("pmass"))
                exodata["planet"]["m_unit"] = str(self.get_argument("m_unit"))
            #baseline 
            exodata["observation"]["baseline"] = float(self.get_argument("baseline"))
            exodata["observation"]["baseline_unit"] = self.get_argument("baseline_unit")
            try:
                exodata["observation"]["target_acq"] = self.get_argument("TA") == 'on'
            except:
                exodata["observation"]["target_acq"] = False

            exodata["observation"]["noccultations"] = float(self.get_argument("numtrans"))
            exodata["observation"]["sat_level"] = float(self.get_argument("satlevel"))
            exodata["observation"]["sat_unit"] = self.get_argument("sat_unit")


            # noise floor, set to 0.0 of no values are input
            try:
                observation_type = self.get_argument("noiseModel")
                if observation_type == "user":
                    # process noise file
                    fileinfo_noise = self.request.files['noiseFile'][0]
                    fname_noise = fileinfo_noise['filename']
                    extn_noise = os.path.splitext(fname_noise)[1]
                    cname_noise = id + 'noise' + extn_noise
                    fh_noise = open(os.path.join(__TEMP__, cname_noise), 'wb')
                    fh_noise.write(fileinfo_star['body'])
                    fh_noise.close()
                    exodata["observation"]["noise_floor"] = os.path.join(__TEMP__, cname_noise)
                else:
                    exodata["observation"]["noise_floor"] = float(self.get_argument("noisefloor"))
            except:
                exodata["observation"]["noise_floor"] = 0.0

        instrument = self.get_argument("instrument").lower()
        if instrument == "miri":
            with open(os.path.join(os.path.dirname(__file__), "reference", "miri_input.json")) as data_file:
                pandata = json.load(data_file)       
                mirimode = self.get_argument("mirimode")
                if (mirimode == "lrsslit"):
                    pandata["configuration"]["instrument"]["mode"] = mirimode
                    pandata["configuration"]["instrument"]["aperture"] = "lrsslit"
                    pandata["configuration"]["detector"]["subarray"] = "full"

        if instrument == "nirspec":
            with open(os.path.join(os.path.dirname(__file__), "reference", "nirspec_input.json")) as data_file:
                pandata = json.load(data_file)  
                nirspecmode = self.get_argument("nirspecmode")
                pandata["configuration"]["instrument"]["disperser"] = nirspecmode[0:5]
                pandata["configuration"]["instrument"]["filter"] = nirspecmode[5:11]
                pandata["configuration"]["detector"]["subarray"] = self.get_argument("nirspecsubarray")

        if instrument == "nircam":
            with open(os.path.join(os.path.dirname(__file__), "reference", "nircam_input.json")) as data_file:
                pandata = json.load(data_file) 
                pandata["configuration"]["instrument"]["filter"] = self.get_argument("nircammode")
                pandata["configuration"]["detector"]["subarray"] = self.get_argument("nircamsubarray")

        if instrument == "niriss":
            with open(os.path.join(os.path.dirname(__file__), "reference", "niriss_input.json")) as data_file:
                pandata = json.load(data_file)
                nirissmode = self.get_argument("nirissmode")
                pandata["configuration"]["detector"]["subarray"] = nirissmode

        pandata['configuration']['instrument']['instrument'] = instrument

        # write in optimal groups or set a number
        try:
            pandata["configuration"]["detector"]["ngroup"] = int(self.get_argument("optimize"))
        except: 
            pandata["configuration"]["detector"]["ngroup"] = self.get_argument("optimize")

        finaldata = {"pandeia_input": pandata, "pandexo_input": exodata}

        #PandExo stats
        try: 
            jwst_log(finaldata)
        except: 
            pass

        task = self.executor.submit(wrapper, finaldata)


        self._add_task(id, self.get_argument("calcName"), task, form_data)

        response = self._get_task_response(id)
        response['info'] = {}
        response['location'] = '/calculation/status/{}'.format(id)


        self.write(dict(response))
        self.redirect("../dashboard")


class ResolveHandler(tornado.web.RequestHandler):
    """
    Resolves a planet by name and returns data on its system
    """
    def get(self):
        name = self.get_argument("name")

        try:
            planet_data = get_target_data(name)[0]
        except:
            planet_data = None
        
        self.write(json.dumps(planet_data))


            
class CalculationNewHSTHandler(BaseHandler):
    """
    This request handler deals with processing the form data and submitting
    a new HST calculation task to the parallelized workers.
    """

    def get(self, id=None):
        try: 
            self.header= pd.read_sql_table('header',db_fort)
        except:
            self.header = pd.DataFrame({
            'temp': ['NO GRID DB FOUND'],
            'ray' : ['NO GRID DB FOUND'],
            'flat':['NO GRID DB FOUND']})
        with open(os.path.join(os.path.dirname(__file__), "reference",
                               "exo_input.json")) as data_file:
            exodata = json.load(data_file)


        form_data = None
        if id is not None:            
            form_data = self.buffer[id].form_data
            
        all_planets =  pd.read_csv('https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query=select+pl_name+from+PSCompPars&format=csv')
        all_planets = sorted(all_planets['pl_name'].values)        
        unique_temps = sorted(self.header.temp.unique())
        self.render("newHST.html", id=id,
                    temp=list(map(str, unique_temps)),
                    data=exodata,
                    data_json=json.dumps(form_data),
                    planets=all_planets)

    def post(self):
        """
        The post method contains the retured data from the form data (
        accessed by using `self.get_argument(...)` for specific arguments,
        or `self.request.body` to grab the entire returned object.
        """
        form_data = {}
        for key in self.request.arguments:
            form_data[key] = self.get_argument(key)

        id = str(uuid.uuid4())+'h'
      
        with open(os.path.join(os.path.dirname(__file__), "reference",
                        "exo_input.json")) as data_file:
            exodata = json.load(data_file)
            exodata["telescope"] = 'hst'

            #star
            exodata["star"]["jmag"]         = float(self.get_argument("Jmag"))
            try:
                #only needed for higher accuracy
                exodata["star"]["hmag"]     = float(self.get_argument("Hmag"))
            except:
                exodata["star"]["hmag"]     = None

            exodata["star"]["radius"] = float(self.get_argument("rstarc"))
            exodata["star"]["r_unit"] = str(self.get_argument("rstar_unitc"))
            try:
                #only needed for secondary eclipse
                exodata["star"]["temp"] = float(self.get_argument("stempc"))
            except:
                exodata["star"]["temp"] = None

            #planet
            exodata["planet"]["radius"] = float(self.get_argument("refradc"))
            exodata["planet"]["r_unit"] = str(self.get_argument("r_unitc"))
            depth = exodata["planet"]["radius"]**2 / ((exodata["star"]["radius"]
                                                        *u.Unit(exodata["star"]["r_unit"]) )
                                                            .to(u.Unit(exodata["planet"]["r_unit"]))).value**2

            exodata["planet"]["depth"]      = depth
            exodata["planet"]["i"]          = float(self.get_argument("i"))
            exodata["planet"]["ars"]        = float(self.get_argument("ars"))
            exodata["planet"]["period"]     = float(self.get_argument("period"))
            exodata["planet"]["ecc"]        = float(self.get_argument("ecc"))
            try:
                exodata["planet"]["w"]      = float(self.get_argument("w"))
            except:
                exodata["planet"]["w"]      = 90.
            exodata["planet"]["transit_duration"]   = float(self.get_argument("transit_duration"))

            # planet model
            exodata["planet"]["type"] = self.get_argument("planetModel")

            if exodata["planet"]["type"] == "user":
                # process planet file
                fileinfo_plan = self.request.files['planFile'][0]
                fname_plan = fileinfo_plan['filename']
                extn_plan = os.path.splitext(fname_plan)[1]
                cname_plan = id+'planet' + extn_plan
                fh_plan = open(os.path.join(__TEMP__, cname_plan), 'wb')
                fh_plan.write(fileinfo_plan['body'])
                fh_plan.close()

                exodata["planet"]["exopath"] = os.path.join(__TEMP__, cname_plan)
                exodata["planet"]["w_unit"] = self.get_argument("planwunits")
                exodata["planet"]["f_unit"] = self.get_argument("planfunits")

            elif exodata["planet"]["type"] == "constant":                               
                if self.get_argument("constant_unit") == 'fp/f*':
                    exodata["planet"]["temp"] = float(self.get_argument("ptempc"))
                    exodata["planet"]["f_unit"] = 'fp/f*'
                elif self.get_argument("constant_unit") == 'rp^2/r*^2':
                    exodata["planet"]["f_unit"] = 'rp^2/r*^2'

            elif exodata["planet"]["type"] == "grid":
                exodata["planet"]["mass"] = float(self.get_argument("pmass"))
                exodata["planet"]["m_unit"] = str(self.get_argument("m_unit"))
                exodata["planet"]["temp"] = float(self.get_argument("ptempg"))
                exodata["planet"]["chem"] = str(self.get_argument("pchem"))
                exodata["planet"]["cloud"] = self.get_argument("cloud") 

            exodata["observation"]["noise_floor"]           = 0.0
            exodata["calculation"]                          = 'scale'

        if (self.get_argument("instrument")=="STIS"): 
            with open(os.path.join(os.path.dirname(__file__), "reference",
                               "stis_input.json")) as data_file:   
                pandata = json.load(data_file)       
                stismode = self.get_argument("stismode")
        if (self.get_argument("instrument")=="WFC3"): 
            with open(os.path.join(os.path.dirname(__file__), "reference",
                               "wfc3_input.json")) as data_file:
                pandata = json.load(data_file)  
                pandata["configuration"]['detector']['subarray']    = self.get_argument("subarray")
                pandata["configuration"]['detector']['nsamp']       = int(self.get_argument("nsamp"))
                pandata["configuration"]['detector']['samp_seq']    = self.get_argument("samp_seq")
                pandata["configuration"]['instrument']['disperser'] = self.get_argument("wfc3mode")
            try: 
                pandata["strategy"]["norbits"]           = int(self.get_argument("norbits"))
            except:
                pandata["strategy"]["norbits"]           = None
            exodata["observation"]["noccultations"]         = int(self.get_argument("noccultations"))
            pandata["strategy"]["nchan"]                 = int(self.get_argument("nchan"))
            pandata["strategy"]["scanDirection"]         = self.get_argument("scanDirection")
            pandata["strategy"]["useFirstOrbit"]         = self.get_argument("useFirstOrbit").lower() == 'true'
            try:
                pandata["strategy"]["windowSize"]        = float(self.get_argument("windowSize"))
            except:
                pandata["strategy"]["windowSize"]        = 20.
            pandata["strategy"]["schedulability"]           = self.get_argument("schedulability")
        try:
            calc_ramp = self.get_argument("ramp")

            calc_ramp = True
        except: 
            calc_ramp = False


        pandata['strategy']['calculateRamp'] = calc_ramp
        pandata['strategy']['targetFluence'] = float(self.get_argument("targetFluence"))

        #import pickle as pk 
        #a = pk.load(open('/Users/natashabatalha/Desktop/JWST/testing/ui.pk','rb'))
        #pandata = a['pandeia_input']
        #exodata  = a['pandexo_input']

        finaldata = {"pandeia_input": pandata , "pandexo_input":exodata}
        #PandExo stats
        try: 
            hst_log(finaldata)
        except: 
            pass

        task = self.executor.submit(wrapper, finaldata)

        self._add_task(id, self.get_argument("calcName"), task, form_data)

        response = self._get_task_response_hst(id)
        response['info'] = {}
        response['location'] = '/calculation/statushst/{}'.format(id)


        self.write(dict(response))
        self.redirect("../dashboardhst")

class CalculationStatusHandler(BaseHandler):
    """
    Handlers returning the status of a particular JWST calculation task.
    """
    def get(self, id):
        response = self._get_task_response(id)

        if self.request.connection.stream.closed():
            return

        self.write(dict(response))

        
class CalculationStatusHSTHandler(BaseHandler):
    """
    Handlers returning the status of a particular HST calculation task.
    """
    def get(self, id):
        response = self._get_task_response_hst(id)

        if self.request.connection.stream.closed():
            return

        self.write(dict(response))                

class CalculationDownloadTextHandler(BaseHandler):
    def get(self, id):
        result = self._get_task_result(id)
  
        if self.request.connection.stream.closed():
            return

        self.set_header('Content-Type', 'text/plain; charset=utf-8')
        self.set_header('Content-Disposition', 'attachment; filename=sim_obs.txt')

        if "FinalSpectrum" in result:
            #JWST result
            output = "#wave spectrum spectrum_w_rand error_w_floor\n"
            spec = result["FinalSpectrum"]
            for i in range(len(spec["wave"])):
                output += "{} {} {} {}\n".format(
                    spec["wave"][i], spec["spectrum"][i], spec["spectrum_w_rand"][i], spec["error_w_floor"][i])
        elif "planet_spec" in result:
            #HST result
            output = "#wave spectrum error\n"
            spec = result["planet_spec"]
            for i in range(len(spec["binwave"])):
                output += "{} {} {}\n".format(round(spec["binwave"][i], 5), spec["binspec"][i], spec["error"])
        else:
            return None    
                
        self.write(output)
        self.finish()

        
class CalculationDownloadHandler(BaseHandler):
    """
    Handlers returning the downloaded data of a particular calculation task.
    Handlers returning the status of a particular calculation task.
    """
    def get(self, id):
        result = self._get_task_result(id)
  
        if self.request.connection.stream.closed():
            return
        file_name = "ETC-calculation" +id+".p"
 
        with open(os.path.join(__TEMP__,file_name), "wb") as f:
            pickle.dump(result, f)
 
        buf_size = 4096
        self.set_header('Content-Type', 'application/octet-stream')
        self.set_header('Content-Disposition',
                        'attachment; filename=' + file_name)
 
        with open(os.path.join(__TEMP__,file_name), "rb") as f:
            while True:
                data = f.read(buf_size)
                if not data:
                    break
                self.write(data)
        
        allfiles = os.listdir(__TEMP__)
        for i in allfiles:
            if i.find(id) != -1:
                os.remove(os.path.join(__TEMP__,i))
        self.finish()


      

class CalculationDownloadPandInHandler(BaseHandler):
    """
    Handlers returning the downloaded data of a particular calculation task.
    Handlers returning the status of a particular calculation task.
    """
    def get(self, id):
        result = self._get_task_result(id)
  
        if self.request.connection.stream.closed():
            return
        file_name = "PandExo-Input-file"+id+".txt"
 
        #with open(os.path.join(__TEMP__,file_name), "w") as f:
        #    pickle.dump(result, f)
        np.savetxt(os.path.join(__TEMP__,file_name), np.transpose([result['w'], result['alpha']]))
        
        buf_size = 4096
        self.set_header('Content-Type', 'application/octet-stream')
        self.set_header('Content-Disposition',
                        'attachment; filename=' + file_name)
 
        with open(os.path.join(__TEMP__,file_name), "rb") as f:
            while True:
                data = f.read(buf_size)
                if not data:
                    break
                self.write(data)
        
        allfiles = os.listdir(__TEMP__)
        for i in allfiles:
            if i.find(id) != -1:
                os.remove(os.path.join(__TEMP__,i))


        self.finish()



class CalculationViewHandler(BaseHandler):
    """
    This handler deals with passing the results from Pandeia to the
    `create_component_jwst` function which generates the Bokeh interative plots.
    """
    def get(self, id):
        
        result = self._get_task_result(id)
        
        script, div = create_component_jwst(result)
        div['timing_div'] = result['timing_div']
        div['input_div'] = result['input_div'] 
        div['warnings_div'] = result['warnings_div']

        #delete files
        allfiles = os.listdir(__TEMP__)
        for i in allfiles:
            if i.find(id) != -1:
                os.remove(os.path.join(__TEMP__,i))

        self.render("view.html", script=script, div=div, id=id)



class CalculationViewHSTHandler(BaseHandler):
    """
    This handler deals with passing the results from Pandeia to the
    `create_component_hst` function which generates the Bokeh interative plots.
    """
    def get(self, id):
        result = self._get_task_result(id)
        script, div = create_component_hst(result)
        div['info_div'] = result['info_div']
        self.render("viewhst.html", script=script, div=div, id=id)


def main():
    tornado.options.parse_command_line()
    BaseHandler.executor = ProcessPoolExecutor(max_workers=options.workers)
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port)
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
