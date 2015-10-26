
from re import sub
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime
import os, time, errno, string, inspect, urllib2, urlparse, feedparser 


def metric(f):
    f.is_metric = True
    return f

def pgSQL_type_conversion(f):
    conversion_type = f.__name__.replace('convert_', '')
    exec( 't = {0}'.format(conversion_type) )
    f.__conversionType__ = t
    return f

def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc: 
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise

#TODO daemonize 
#TODO add postgresql server to store all data (and to acomplish todo above ^^)

#TODO hide http requests behind array of proxies (or tor)
#TODO add fields

class AptFeed(object): 

    """
    Loop over a given CraigsList RSS feed for Apartment Listings and save metrics that predict property value to a PostgreSQL database

    @metric functions:
        these accept a BeautifulSoup (html) object and return a dictionary whose keys map to the postgresql database fields, and values are that listing's coresponding values

        this convention allows new metrics to be added to the AptFeed class without any additional overhead. All metrics can be automatically called, and new db fields
        can be automatically added

    """

    no_geo  = {'latitude':null, 'longitude':null}
    nan     = float('nan')
    null    = 'NULL'

    feed = None
    database = None
    postgresql_types = {int:'int4', float:'float4', str:'text', datetime:'timestamp'}

    def __init__(self, rss_url, base_dir, soup_parser='lxml'):
        self.rss_url = rss_url
        self.filesystem_base = base_dir
        self.soup_parser = soup_parser

        methods = inspect.getmembers(self, predicate=inspect.ismethod)
        self.metric_methods     = [method for (name, method) in methods if 'is_metric' in dir(method)]
        self.type_conversions   = { method.__conversionType__:method for (name, method) in methods if '__conversionType__' in dir(method)}


    def process_feed(self):
        for item in self.feed['items']:
            soup = self.soup(item['link'])
            metrics = coalesce_metrics()
            self.save_items(soup)

    def update_feed(self):
        self.feed = feedparser.parse(self.rss_url, modified=(self.feed.modified if self.feed != None else None))
        return self.feed.status

    def soup(self, url):
        html = urllib2.urlopen(url).read() #TODO hide with random list of proxies
        return BeautifulSoup(html, self.soup_parser)

    @metric
    def get_rent(self, soup):
        rent = soup.find('span', {'class':'price'}).text
        rent = self.str_to_float(rent)
        return {'rent':rent}

    @metric
    def get_geo(self, soup):
        map_div = soup.find('div', {'id':'map'})
        geo_keys = ['data-latitude', 'data-longitude']  # this div also contains an "accuracy" metric -- maybe useful, probably not
        if map_div == None or any(key not in map_div.attrs for key in geo_keys): return self.no_geo 
        
        return { k.replace('data-', ''):v for k,v in map_div.attrs.items() }

    @metric
    def get_size_metrics(self, soup):
        db_fields = {}
        size_metrics = {'ft2':self.null, 'br':self.null}
        housing_info = soup.find('span', {'class':'housing'}).text
        if housing_info == None: return {}
        housing_info = [part.strip() for part in  housing_info.split('-')]
        for info in housing_info:
            for metric in size_metrics:
                if metric in info:
                    db_fields[metric] = self.force_int( info.replace(metric, '') )
        return db_fields
        
    @metric 
    def get_url(self, soup):
        url = soup.link.attrs['href']
        return {'url':url}

    @metric
    def get_post_date(self, soup):
        date_str = soup.find('div', {'class':'postinginfos'}).findAll('p', {'class':'postinginfo'})[1].find('time').attrs['datetime']
        dt = datetime.parser.parse(date_str)
        return {'created':dt}

    def coalesce_metrics(self):
        db_fields = {}
        for field in [f(soup) for f in self.metric_methods]:
            db_fields.update(field)
        return db_fields 

    def pgSQL_insert(self, fields):
        pass
       
    def save_items(self, soup, apt_id):
        apt_dir = str(apt_id)
        base_dir = os.path.join(self.filesystem_base, apt_dir) 
        img_dir = os.path.join(base_dir, 'img')
        mkdir_p(base_dir)

        self.save_images(soup, img_dir)
        self.save_html(soup, base_dir)

    def save_html(self, soup, apt_id):
        apt_dir = str(apt_id)
        base_dir = os.path.join(self.filesystem_base, apt_dir) 
        html_file = os.path.join(base_dir, 'html')
        with open(html_file, 'w+') as f:
            html = str(soup.html)
            f.write(html)
        return True
 
    def save_images(self, soup, img_dir):
        thumbs = soup.find('div', {'id':'thumbs'}).findAll('a')
        if thumbs == None: return 0
        mkdir_p(img_dir)

        for i, thumb in enumerate(thumbs):
            img_data = urllib2.urlopen(thumb['href'] ).read()       #TODO hide with random list of proxies
            img_path = urlparse.urlparse(thumb['href']).path 
            img_ext =  os.path.splitext(img_path)[1]
            path = os.path.join(img_dir, '{0}{1}'.format(i, img_ext))
            with open(path, 'wb') as f:
                f.write(img_data)
        return i

    def str_to_float(self, string):
        return float(sub(r'[^\d.]', '', string))

    def force_int(self, string):
        return int(sub(r'[^\d]', '', string))   #CL seems to enforce ints for price and square footage. Taking the risk for now. Just want it running

    @pgSQL_type_conversion
    def convert_int(self, val):
        if type(val) != int: return ''
        return str(int)

    @pgSQL_type_conversion
    def convert_float(self, val):
        if type(val) != float: return ''
        return str(val)

    @pgSQL_type_conversion
    def convert_datetime(self, val):
        if type(val) != datetime: return ''
        f = '%Y-%m-%d %H:%M:%S'
        return val.strftime(f) 




if __name__ == '__main__':
    
    link = r'https://newyork.craigslist.org/search/aap?format=rss&hasPic=1&minSqft=1'       # this forces the listing to have a picture AND square footage
                                                                                            # consider changing to allow for no square footage...much harder
                                                                                            # to extract bedroom and size metrics..but may lose some gems
    #TODO move this to a unittest suite 
    #TODO you should be ashamed of yourself 
    #TODO YOU HEATHEN

    parser = AptFeed(link, os.path.expanduser('~/img_tmp') )
    a = 'https://newyork.craigslist.org/mnh/fee/5280880697.html'
    b = 'https://newyork.craigslist.org/mnh/fee/5280880497.html'
    c = 'https://newyork.craigslist.org/que/fee/5280918276.html'
    urls = [a, b, c]
    for i, url in enumerate(urls):
        soup = parser.soup(url)
        parser.coalesce_metrics()
        parser.save_items(soup, i)



