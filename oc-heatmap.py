#!/usr/bin/env python3

#
# Copyright (c) 2017 Florian Pigorsch <mail@florian-pigorsch.de>
#
# MIT licensed (see LICENSE for details)
#
# Create a js/html based heatmap for active geocaches of https://www.opencaching.de/
#


import logging
import os
import shutil
import sys
import tempfile


class OCHeatmapGenerator:
    url = 'http://www.opencaching.de/xml/ocxml15.php'

    def __init__(self):
        self.temp_dir = None
        self.output_dir = 'out'
        self.base_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
        self.log = logging.getLogger('oc-heatmap')
        self.log.setLevel(logging.ERROR)
        ch = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        ch.setFormatter(formatter)
        self.log.addHandler(ch)
        self.session_id = None
        self.time_stamp = None
        self.files = 0
        self.grid = {}
        self.cache_count = 0

    def set_output_dir(self, d):
        self.output_dir = d

    def set_verbose(self, v):
        if v:
            self.log.setLevel(logging.INFO)
        else:
            self.log.setLevel(logging.ERROR)

    def _download(self, url, target_file_name):
        import urllib.request
        self.log.info('requesting file: {}'.format(target_file_name))
        if os.path.isfile(target_file_name):
            return
        self.log.info('fetching: {}'.format(url))
        response = urllib.request.urlopen(url)
        data = response.read()
        with open(target_file_name, 'wb') as f:
            f.write(data)

    @staticmethod
    def _get_text(nodelist):
        s = ""
        for node in nodelist:
            if node.nodeType == node.TEXT_NODE:
                s = s + node.data
        return s

    def _process_index(self):
        from xml.dom import minidom
        import time
        import math
        target_file_name = os.path.join(self.temp_dir, 'index.xml')
        earliest_time = '20050801000000'
        self._download('{}?modifiedsince={}&cache=1'.format(self.url, earliest_time), target_file_name)
        self.time_stamp = time.localtime(os.path.getmtime(target_file_name))
        xml = minidom.parse(target_file_name)
        self.session_id = self._get_text(xml.getElementsByTagName('sessionid')[0].childNodes)
        self.log.info('session_id: {}'.format(self.session_id))
        records = int(xml.getElementsByTagName('records')[0].attributes['cache'].value)
        self.files = math.ceil(records / 500)
        self.log.info('records: {} => files: {}'.format(records, self.files))

    def _process_file(self, file_index):
        from xml.dom import minidom
        import gzip
        target_file_name = '{}/file{}.xml.gz'.format(self.temp_dir, file_index)
        self._download('{}?sessionid={}&file={}&charset=utf-8&cdata=1&xmldecl=1&ocxmltag=1&doctype=0&zip=gzip'
                       .format(self.url, self.session_id, file_index), target_file_name)
        if os.path.getsize(target_file_name) < 100:
            self.log.info('file seems to be almost empty => skipping...')
            return
        with gzip.open(target_file_name, 'rb') as f:
            caches = 0
            added = 0
            xml = minidom.parse(f)
            for cache in xml.getElementsByTagName('cache'):
                caches += 1
                if self._process_cache(cache):
                    added += 1
            self.log.info('added caches: {}/{}'.format(added, caches))

    def _process_cache(self, cache_xml):
        status_el = cache_xml.getElementsByTagName('status')[0]
        status_id = status_el.attributes['id'].value
        if status_id != '1':
            return False
        lat = float(self._get_text(cache_xml.getElementsByTagName('latitude')[0].childNodes))
        lon = float(self._get_text(cache_xml.getElementsByTagName('longitude')[0].childNodes))
        key = '{:.2f}/{:.2f}'.format(lat, lon)
        if key in self.grid:
            self.grid[key] += 1
        else:
            self.grid[key] = 1
        self.cache_count += 1
        return True

    def _write_data_file(self):
        target_file_name = '{}/data.js'.format(self.output_dir)
        self.log.info('creating file: {}'.format(target_file_name))
        with open(target_file_name, 'w') as f:
            f.write('var data = [\n')
            max_v = 0
            for k, v in self.grid.items():
                if v > max_v:
                    max_v = v
            for k, v in self.grid.items():
                lat_lon = k.split('/')
                f.write('[{}, {}, {}],\n'.format(lat_lon[0], lat_lon[1], v/float(max_v)))
            f.write('];\n')

    def _write_index_file(self):
        import time
        target_file_name = '{}/index.html'.format(self.output_dir)
        self.log.info('creating file: {}'.format(target_file_name))
        template = os.path.join(self.base_dir, 'templates', 'index.html')
        self.log.info('processing template file: {}'.format(template))
        with open(template, 'r') as f_in, open(target_file_name, 'w') as f_out:
            data = f_in.read()\
                .replace('@COUNT@', '{}'.format(self.cache_count))\
                .replace('@DATE@', time.strftime('%Y-%m-%d', self.time_stamp))
            f_out.write(data)

    def _ensure_dir(self, dir_name):
        if not os.path.exists(dir_name):
            self.log.info('creating dir: {}'.format(dir_name))
            os.mkdir(dir_name)

    def run(self, keeptempdir):
        self.temp_dir = tempfile.mkdtemp(prefix='oc-heatmap-')
        self.log.info('using temp dir: {}'.format(self.temp_dir))
        self.log.info('using output dir: {}'.format(self.output_dir))
        self._ensure_dir(self.output_dir)
        self._process_index()
        for file_index in range(1, self.files + 1):
            self.log.info('file {}/{}'.format(file_index, self.files))
            self._process_file(file_index)
        self._write_index_file()
        self._write_data_file()
        if not keeptempdir:
            self.log.info('deleting temp dir: {}'.format(self.temp_dir))
            shutil.rmtree(self.temp_dir)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', help='verbose output', action='store_true')
    parser.add_argument('-k', '--keeptempdir', help='don\'t delete the temp dir', action='store_true')
    parser.add_argument('-o', '--outputdir', help='select output dir', type=str, default='out')
    args = parser.parse_args()

    gen = OCHeatmapGenerator()
    gen.set_output_dir(args.outputdir)
    gen.set_verbose(args.verbose)
    gen.run(args.keeptempdir)
