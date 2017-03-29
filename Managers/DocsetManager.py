import json
import os
import ui
import requests
import xml.etree.cElementTree
import threading
import ui
import time
import math
import tarfile
import plistlib
import console
import sqlite3
from objc_util import ns, ObjCClass

class Docset(object):
	def __init__(self):
		self.displayName = ''
		self.downloaded = False
		
class DocsetManager (object):
	def __init__(self, iconPath, typeIconPath, serverManager):
		self.docsets = []
		self.downloading = []
		self.docsetFolder = 'Docsets'
		self.plistPath = 'Contents/Info.plist'
		self.indexPath = 'Contents/Resources/docSet.dsidx'
		self.iconPath = iconPath
		self.typeIconPath = typeIconPath
		self.headers = {
    'User-Agent': 'PyDoc-Pythonista'
    }
		self.__createDocsetFolder()
		self.docsetFeeds = self.__getDocsetFeeds()
		self.serverManager = serverManager
		self.downloadThreads = []
		self.uiUpdateThreads = []
		self.workThreads = []
		
	def __createDocsetFolder(self):
		if not os.path.exists(self.docsetFolder):
			os.mkdir(self.docsetFolder)
		
	def __getDocsetFeeds(self):
		with open('feeds.json') as json_data:
			data = json.load(json_data)
			feeds = []
			for feed in data:
				f = {'name':self.__getDocsetName(feed['feed']),'detailString':'',
				'feed':feed['feed'],
				'iconName':feed['icon'],
				'isCustom':False,
				'feedUrl':'http://kapeli.com/feeds/'+feed['feed'],
				'aliases':feed['aliases'],
				'hasVersions':feed['hasVersions']}
				if feed['feed'] == 'SproutCore.xml':
					f['isCustom'] = True
					f['feedUrl'] = 'http://docs.sproutcore.com/feeds/' + feed['feed']
				f['image'] = self.__getIconWithName(feed['icon'])
				feeds.append(f)
			return feeds
		
	def getAvailableDocsets(self):
		docsets = self.__getOnlineDocsets()
		for d in self.__getDownloadedDocsets():
			for c in docsets:
				if c['name'] == d['name']:
					c['status'] = 'installed'
					c['path'] = d['path']
		for d in self.__getDownloadingDocsets():
			for c in docsets:
				if c['name'] == d['name']:
					c['status'] = d['status']
					try:
						c['stats'] = d['stats']
					except KeyError:
						c['stats'] = 'downloading'
		return docsets
	
	def getDownloadedDocsets(self):
		ds = []
		for dd in self.__getDownloadedDocsets():
			for feed in self.docsetFeeds:
				if dd['name'] == feed['name']:
					feed['path'] = dd['path']
					ds.append(feed)
		return ds
	
	def __docsetFeedToDocset(self, feed):
		return feed
			
	def __getDownloadedDocsets(self):
		ds = []
		folder = os.path.join(os.path.abspath('.'), self.docsetFolder)
		for dir in os.listdir(folder):
			if os.path.isdir(os.path.join(folder,dir)):
				pl = plistlib.readPlist(
				os.path.join(folder,dir, self.plistPath))
				name = pl['CFBundleName']
				if name == 'Sails.js':
					name = 'SailsJS'
				elif name == 'Backbone.js':
					name = 'BackboneJS'
				ds.append({'name':name,'path':os.path.join(folder,dir)})
		return ds

	def __getDownloadingDocsets(self):
		return self.downloading
	
	def __getOnlineDocsets(self):
		feeds = self.__getDocsetFeeds()
		onlineDocsets = []
		for f in feeds:
			obj = self.__docsetFeedToDocset(f)
			obj['status'] = 'online'
			onlineDocsets.append(obj)
		return onlineDocsets
	
	def __getDocsetName(self, feed):
		name = feed.replace('.xml','')
		name = name.replace('_',' ')
		if name == 'NET Framework':
			name = '.NET Framework'
		return name
	
	def __getIconWithName(self, name):
		
		imgPath = os.path.join(os.path.abspath('.'), self.iconPath, name+'.png')
		return ui.Image.named(imgPath)
		
	def __getTypeIconWithName(self, name):
		
		imgPath = os.path.join(os.path.abspath('.'), self.typeIconPath , name+'.png')
		return ui.Image.named(imgPath)
	
	def __checkDocsetCanDownload(self, docset):
		cont = True
		feed = docset['feed']
		title = ''
		message = ''
		if feed == 'DOM.xml':
			cont = False
			title = 'DOM Documentation'
			message = 'There is no DOM docset. DOM documentation can be found in the JavaScript docset. Please install the JavaScript docset instead.'
		elif feed == 'RubyMotion.xml':
			cont = False
			title = 'RubyMotion Documentation'
			message = 'RubyMotion had to remove its API documentation due to legal reasons. Please contact the RubyMotion team for more details.\n\nIn the meantime, you can use the Apple API Reference docset instead.'
		elif feed == 'Apple_API_Reference.xml':
			cont = False
			title = 'Apple API Reference'
			message = 'To install the Apple API Reference docset you need to:\n\n1. Use Dash for macOS to install the Apple API Reference docset from Preferences > Downloads\n2. Go to Preferences > Docsets, right click the Apple API Reference docset and select \"Generate iOS Compatible Docset\"\n3. Transfer the resulting docset using iTunes File Sharing'
		elif feed == 'Apple_Guides_and_Sample_Code.xml':
			cont = False
			title = 'Apple Guides and Sample Code'
			message = 'To install the Apple Guides and Sample Code docset you need to:\n\n1. Download the docset in Xcode 8\'s Preferences > Components > Documentation\n2.Transfer it to Dash for iOS using iTunes File Sharing'
		elif feed == 'OS_X.xml' or feed == 'macOS.xml' or feed == 'watchOS.xml' or feed == 'iOS.xml' or feed == 'tvOS.xml':
			cont = False
			title = 'Apple API Reference'
			name = docset['name']
			message = 'There is no '+name+' docset. The documentation for '+name+' can be found inside the Apple API Reference docset. \n\nTo install the Apple API Reference docset you need to:\n\n1. Use Dash for macOS to install the docset from Preferences > Downloads\n2. Go to Preferences > Docsets, right click the Apple API Reference docset and select \"Generate iOS-compatible Docset\"\n3. Transfer the resulting docset using iTunes File Sharing'
				
		if cont == False:
			console.alert(title, message,'Ok', hide_cancel_button=True)
		return cont
	
	def downloadDocset(self, docset, action):
		cont = self.__checkDocsetCanDownload(docset)
		if cont and not docset in self.downloading:
			docset['status'] = 'downloading'
			self.downloading.append(docset)
			action()
			workThread = threading.Thread(target=self.__determineUrlAndDownload, args=(docset,action,))
			self.workThreads.append(workThread)
			workThread.start()
			
	def __determineUrlAndDownload(self, docset, action):
		docset['stats'] = 'getting download link'
		action()
		downloadLink = self.__getDownloadLink(docset['feed'])
		downloadThread = threading.Thread(target=self.downloadFile, args=(downloadLink,docset,))
		self.downloadThreads.append(downloadThread)
		downloadThread.start()
		updateThread = threading.Thread(target=self.updateUi, args=(action,downloadThread,))
		self.uiUpdateThreads.append(updateThread)
		updateThread.start()

	def updateUi(self, action, t):
		while t.is_alive():
			action()
			time.sleep(0.5)
		action()
		
	def __getDownloadLink(self, link):
		if link == 'SproutCore.xml':
			data=requests.get('http://docs.sproutcore.com/feeds/' + link).text
			e = xml.etree.ElementTree.fromstring(data)
			for atype in e.findall('url'):
				return atype.text
		server = self.serverManager.getDownloadServer()
		data = requests.get(server.url+link).text
		e = xml.etree.ElementTree.fromstring(data)
		for atype in e.findall('url'):
			if atype.text.find(server.url) >= 0:
				return atype.text
	
	def downloadFile(self, url, docset):
		local_filename = self.docsetFolder+'/'+url.split('/')[-1]
		r = requests.get(url, headers = self.headers, stream=True)
		total_length = r.headers.get('content-length')
		dl = 0
		last = 0
		if os.path.exists(local_filename):
			os.remove(local_filename)
		with open(local_filename, 'wb') as f:
			for chunk in r.iter_content(chunk_size=1024): 
				if chunk: # filter out keep-alive new chunks
					dl += len(chunk)
					f.write(chunk)
					done = 100 * dl / int(total_length)
					docset['stats'] = str(round(done,2)) + '% ' + str(self.convertSize(dl)) + ' / '+ str(self.convertSize(float(total_length)))
		
		r.close()			
		docset['status'] = 'waiting for install'
		self.installDocset(local_filename, docset)
	
	def installDocset(self, filename, docset):
		docset['status'] = 'installing'
		tar = tarfile.open(filename, 'r:gz')
		tar.extractall(path=self.docsetFolder)
		tar.close()
		os.remove(filename)
		self.indexDocset(docset)
	
	def indexDocset(self, docset):
		docset['status'] = 'indexing'
		self.postProcess(docset)
		
	def postProcess(self, docset):
		docset['status'] = 'installed'

	def convertSize(self, size):
		if (size == 0):
			return '0B'
		size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
		i = int(math.floor(math.log(size,1024)))
		p = math.pow(1024,i)
		s = round(size/p,2)
		return '%s %s' % (s,size_name[i])
	
	def getTypesForDocset(self, docset):
		types = []
		path = docset['path']
		indexPath = os.path.join(path, self.indexPath)
		conn = sqlite3.connect(indexPath)
		sql = 'SELECT type FROM searchIndex GROUP BY type'
		c = conn.execute(sql)
		data = c.fetchall()
		conn.close()
		for t in data:
			types.append({'name':t[0], 'image':self.__getTypeIconWithName(t[0])})
		return types
	
	def getIndexesbyTypeForDocset(self, docset, type):
		indexes = []
		path = docset['path']
		indexPath = os.path.join(path, self.indexPath)
		conn = sqlite3.connect(indexPath)
		sql = 'SELECT type, name, path FROM searchIndex WHERE type = \'' + type['name'] + '\''
		c = conn.execute(sql)
		data = c.fetchall()
		conn.close()
		for t in data:
			indexes.append({'type':{'name':t[0], 'image':self.__getTypeIconWithName(t[0])}, 'name':t[1],'path':t[2]})
		return indexes
	
	def getIndexesForDocset(self, docset):
		indexes = []
		path = docset['path']
		indexPath = os.path.join(path, self.indexPath)
		conn = sqlite3.connect(indexPath)
		sql = 'SELECT type, name, path FROM searchIndex'
		c = conn.execute(sql)
		data = c.fetchall()
		conn.close()
		for i in data:
			indexes.append({'type':{'name':t[0], 'image':self.__getTypeIconWithName(t[0])}, 'name':t[1],'path':t[2]})
		return types
		
if __name__ == '__main__':
	dm = DocsetManager()
	print(dm.getAvailableDocsets())
	
