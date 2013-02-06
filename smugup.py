#!/usr/bin/python

import sys, re, urllib, urllib2, urlparse, hashlib, traceback, os.path, ConfigParser, time, datetime
import math
import subprocess
try    : import json
except : import simplejson as json

config = ConfigParser.RawConfigParser()
config.read(os.path.expanduser('~/.smugup'))

##########
# Requirements: Python 2.6 or
#               simplejson from http://pypi.python.org/pypi/simplejson
##########



# This is from http://stackoverflow.com/questions/5925028/urllib2-post-progress-monitoring/5928451#5928451
class Progress(object):
    def __init__(self):
        self._seen = 0.0
        self._progress_updated_at = self._init_at = time.time()
        #self._progress_seen = 0.0

    def update(self, total, size, name):
        self._seen += size
        now = time.time()
        delta_t = now - self._progress_updated_at
        if delta_t > 0.1:
            #self._progress_updated_at = now
            #rate = (self._seen - self._progress_seen) / delta_t
            rate = self._seen / delta_t
            left = math.floor((total - self._seen) / rate)
            pct = (self._seen / total) * 100.0
            #print '\rdelta_t: %.2f, size: %.2f, total: %.2f, rate: %.2f, seen: %.2f, left: %.2f' % (delta_t, size, total, rate, self._seen, left)
            print '\r%s progress: %.2f%% (%.2f KB/s) %s left' % (name, pct, rate/1000, str(datetime.timedelta(seconds=left))),
            sys.stdout.flush()
            #self._progress_seen = self._seen
        if self._seen == total:
            # done reading the file, print stats
            time_took = math.floor(now - self._init_at)
            rate = total / time_took
            print '\r%s progress: %.2f%% (%.2f KB/s) %s total' % (name, 100, rate/1000, str(datetime.timedelta(seconds=time_took))),
            sys.stdout.flush()

class file_with_callback(file):
    def __init__(self, path, mode, callback, *args):
        file.__init__(self, path, mode)
        self.seek(0, os.SEEK_END)
        self._total = self.tell()
        self.seek(0)
        self._callback = callback
        self._args = args

    def __len__(self):
        return self._total

    def read(self, size):
        data = file.read(self, size)
        self._callback(self._total, len(data), *self._args)
        return data


if len(sys.argv) < 3 :
  print 'Usage:'
  print '  upload.py  album [-list] picture1  [picture2  [...]]'
  print
  sys.exit(0)

album_name = sys.argv[1]
su_cookie  = None

def safe_geturl(request) :
  global su_cookie

  # Try up to three times
  for x in range(5) :
    try :
      response_obj = urllib2.urlopen(request)
      response = response_obj.read()
      result = json.loads(response)

      # Test for presence of _su cookie and consume it
      meta_info = response_obj.info()
      if meta_info.has_key('set-cookie') :
        match = re.search('(_su=\S+);', meta_info['set-cookie'])
        if match and match.group(1) != "_su=deleted" :
          su_cookie = match.group(1)
      if result['stat'] != 'ok' : raise Exception('Bad result code')
      return result
    except :
      if x < 4 :
        print "  ... failed, retrying"
      else :
        print "  ... failed, giving up"
        print "  Request was:"
        print "  " + request.get_full_url()
        try :
          print "  Response was:"
          print response
        except :
          pass
        traceback.print_exc()
        #sys.stdin.readline()
        #sys.exit(1)
        return result

def smugmug_request(method, params) :
  global su_cookie
  paramstrings = [urllib.quote(key)+'='+urllib.quote(str(params[key])) for key in params]
  paramstrings += ['method=' + method]
  url = urlparse.urljoin(config.get('Generic', 'api_url'), '?' + '&'.join(paramstrings))
  request = urllib2.Request(url)
  if su_cookie :
    request.add_header('Cookie', su_cookie)
  return safe_geturl(request)

result = smugmug_request('smugmug.login.withPassword',
                         {'APIKey'       : config.get('Account', 'apikey'),
                          'EmailAddress' : config.get('Account', 'email'),
                          'Password'     : config.get('Account', 'password')})
session = result['Login']['Session']['id']

result = smugmug_request('smugmug.albums.get', {'SessionID' : session})
album_id = album_key = None
for album in result['Albums'] :
  if album['Title'] == album_name :
    album_id = album['id']
    album_key = album['Key']
    break
if album_id is None :
  print 'That album does not exist'
  sys.exit(1)

if sys.argv[2] == '-list':
    result = smugmug_request('smugmug.images.get',
                             {'SessionID' : session,
                              'AlbumID'   : album_id,
                              'Heavy'     : True,
                              'AlbumKey'  : album_key})
    album = result['Album']
    for image in album['Images']:
        print image['FileName'] + "\t" + image['URL']
    sys.exit(0)

for filename in sys.argv[2:] :
  #data = open(filename, 'rb').read()
  progress = Progress()
  data = file_with_callback(filename, 'rb', progress.update, filename)
  print 'Uploading ' + filename
  upload_request = urllib2.Request(config.get('Generic', 'upload_url'),
                                   data,
                                   {'Content-Length'  : len(data),
                                    'Content-MD5'     : subprocess.check_output(['md5sum', filename]).split()[0],
                                    'Content-Type'    : 'none',
                                    'X-Smug-SessionID': session,
                                    'X-Smug-Version'  : config.get('Generic', 'api_version'),
                                    'X-Smug-ResponseType' : 'JSON',
                                    'X-Smug-AlbumID'  : album_id,
                                    'X-Smug-FileName' : os.path.basename(filename) })
  result = safe_geturl(upload_request)
  if result['stat'] == 'ok' :
    print "  ... successful"

print 'Done'
# sys.stdin.readline()
