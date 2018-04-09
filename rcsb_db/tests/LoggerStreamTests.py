
import unittest
import logging
from io import StringIO, TextIOWrapper

class MyTest(unittest.TestCase):

    def setUp(self):
        self.stream = StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.log = logging.getLogger('mylogger')
        self.log.setLevel(logging.INFO)
        for handler in self.log.handlers:
            self.log.removeHandler(handler)
        self.log.addHandler(self.handler)

    def testLog(self):
        self.log.info("test")
        self.handler.flush()
        print('[', self.stream.getvalue(), ']')
        self.assertTrue(self.stream.getvalue(), 'test')

    def tearDown(self):
        self.log.removeHandler(self.handler)
        self.handler.close()


if __name__ == '__main__':
    unittest.main()
