##
# File:    CockroachDbLoaderCockroachDbTests.py
# Author:  J. Westbrook
# Date:    10-Feb-2018
# Version: 0.001
#
# Updates:
#
#   All s###  2-Apr-2018 jdw update for refactored api's an utils
##
"""
Tests for creating and loading distributed rdbms database using PDBx/mmCIF data files
and external schema definitions using CockroachDb services -  Covers BIRD, CCD and PDBx/mmCIF
model files -

The following test settings from the configuration will be used will a fallback to localhost/26257.

    COCKROACH_DB_USER_NAME
      [COCKROACH_DB_PW]
    COCKROACH_DB_NAME
    COCKROACH_DB_HOST

See also the load length limit for each file type for testing  -  Set to None to remove -

        self.__fileLimit = 100

"""

__docformat__ = "restructuredtext en"
__author__ = "John Westbrook"
__email__ = "jwest@rcsb.rutgers.edu"
__license__ = "Apache 2.0"


import sys
import os
import time
import unittest

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s]-%(module)s.%(funcName)s: %(message)s')
logger = logging.getLogger()

HERE = os.path.abspath(os.path.dirname(__file__))
TOPDIR = os.path.dirname(os.path.dirname(HERE))

try:
    from rcsb_db import __version__
except Exception as e:
    sys.path.insert(0, TOPDIR)
    from rcsb_db import __version__

from rcsb_db.cockroach.CockroachDbUtil import CockroachDbQuery
from rcsb_db.cockroach.CockroachDbLoader import CockroachDbLoader
from rcsb_db.cockroach.Connection import Connection
#
from rcsb_db.sql.SqlGen import SqlGenAdmin

try:
    from mmcif.io.IoAdapterCore import IoAdapterCore as IoAdapter
except Exception as e:
    from mmcif.io.IoAdapterPy import IoAdapterPy as IoAdapter

from rcsb_db.utils.ConfigUtil import ConfigUtil
from rcsb_db.utils.ContentTypeUtil import ContentTypeUtil

import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s]-%(module)s.%(funcName)s: %(message)s')
logger = logging.getLogger()


class CockroachDbLoaderCockroachDbTests(unittest.TestCase):

    def __init__(self, methodName='runTest'):
        super(CockroachDbLoaderCockroachDbTests, self).__init__(methodName)
        self.__verbose = True
        self.__createFlag = False

    def setUp(self):
        self.__verbose = True
        self.__numProc = 2
        self.__fileLimit = 100
        self.__workPath = os.path.join(HERE, "test-output")
        self.__mockTopPath = os.path.join(TOPDIR, "rcsb_db", "data")
        configPath = os.path.join(TOPDIR, 'rcsb_db', 'data', 'dbload-setup-example.cfg')
        configName = 'DEFAULT'
        self.__cfgOb = ConfigUtil(configPath=configPath, sectionName=configName)
        self.__resourceName = "COCKROACH_DB"
        self.__ctU = ContentTypeUtil(cfgOb=self.__cfgOb, numProc=self.__numProc, fileLimit=self.__fileLimit, mockTopPath=self.__mockTopPath)
        #
        self.__tableIdSkipD = {'ATOM_SITE': True, 'ATOM_SITE_ANISOTROP': True}
        self.__ioObj = IoAdapter(verbose=self.__verbose)
        #
        self.__startTime = time.time()
        logger.debug("Running tests on version %s" % __version__)
        logger.debug("Starting %s at %s" % (self.id(),
                                            time.strftime("%Y %m %d %H:%M:%S", time.localtime())))

    def tearDown(self):
        endTime = time.time()
        logger.debug("Completed %s at %s (%.4f seconds)\n" % (self.id(),
                                                              time.strftime("%Y %m %d %H:%M:%S", time.localtime()),
                                                              endTime - self.__startTime))

    def testConnection(self):
        try:
            with Connection(cfgOb=self.__cfgOb, resourceName=self.__resourceName) as client:
                self.assertNotEqual(client, None)
        except Exception as e:
            logger.exception("Failing with %s" % str(e))
            self.fail()

    def testSchemaCreate(self):
        """  Create table schema (live) for BIRD, chemical component, and PDBx data.
        """
        try:
            sd, _, _ = self.__ctU.getSchemaInfo(contentType='bird')
            ret = self.__schemaCreate(schemaDefObj=sd)
            self.assertEqual(ret, True)
            #
            sd, _, _ = self.__ctU.getSchemaInfo(contentType='chem_comp')
            ret = self.__schemaCreate(schemaDefObj=sd)
            self.assertEqual(ret, True)
            #
            sd, _, _ = self.__ctU.getSchemaInfo(contentType='pdbx')
            ret = self.__schemaCreate(schemaDefObj=sd)
            self.assertEqual(ret, True)
            #
        except Exception as e:
            logger.exception("Failing with %s" % str(e))
            self.fail()

    def testSchemaRemove(self):
        """  Remove table schema (live) for BIRD, chemical component, and PDBx data.
        """
        try:
            sd, _, _ = self.__ctU.getSchemaInfo(contentType='bird')
            ret = self.__schemaRemove(schemaDefObj=sd)
            self.assertEqual(ret, True)
            #
            sd, _, _ = self.__ctU.getSchemaInfo(contentType='chem_comp')
            ret = self.__schemaRemove(schemaDefObj=sd)
            self.assertEqual(ret, True)
            #
            sd, _, _ = self.__ctU.getSchemaInfo(contentType='pdbx')
            ret = self.__schemaRemove(schemaDefObj=sd)
            self.assertEqual(ret, True)
            #
        except Exception as e:
            logger.exception("Failing with %s" % str(e))
            self.fail()

    def testLoadInsertBirdReference(self):

        try:

            sd, _, _ = self.__ctU.getSchemaInfo(contentType='bird')
            if (self.__createFlag):
                self.__schemaCreate(schemaDefObj=sd)
            inputPathList = self.__ctU.getPathList(contentType='bird')
            inputPathList.extend(self.__ctU.getPathList(contentType='bird_family'))
            with Connection(cfgOb=self.__cfgOb, resourceName=self.__resourceName) as client:
                sdl = CockroachDbLoader(schemaDefObj=sd, ioObj=self.__ioObj, dbCon=client, workPath=self.__workPath,
                                        cleanUp=False, warnings='default', verbose=self.__verbose)
                ret = sdl.load(inputPathList=inputPathList, loadType='cockroach-insert', deleteOpt='selected')
                self.assertEqual(ret, True)
        except Exception as e:
            logger.exception("Failing with %s" % str(e))
            self.fail()

    def testLoadInsertManyBirdReference(self):
        try:
            sd, _, _ = self.__ctU.getSchemaInfo(contentType='bird')
            if (self.__createFlag):
                self.__schemaCreate(schemaDefObj=sd)
            inputPathList = self.__ctU.getPathList(contentType='bird')
            inputPathList.extend(self.__ctU.getPathList(contentType='bird_family'))
            with Connection(cfgOb=self.__cfgOb, resourceName=self.__resourceName) as client:
                sdl = CockroachDbLoader(schemaDefObj=sd, ioObj=self.__ioObj, dbCon=client, workPath=self.__workPath,
                                        cleanUp=False, warnings='default', verbose=self.__verbose)
                ret = sdl.load(inputPathList=inputPathList, loadType='cockroach-insert-many', deleteOpt='selected')
                self.assertEqual(ret, True)
        except Exception as e:
            logger.exception("Failing with %s" % str(e))
            self.fail()

    def testLoadInsertChemCompReference(self):

        try:
            sd, _, _ = self.__ctU.getSchemaInfo(contentType='chem_comp')
            if (self.__createFlag):
                self.__schemaCreate(schemaDefObj=sd)
            inputPathList = self.__ctU.getPathList(contentType='chem_comp')
            with Connection(cfgOb=self.__cfgOb, resourceName=self.__resourceName) as client:
                sdl = CockroachDbLoader(schemaDefObj=sd, ioObj=self.__ioObj, dbCon=client, workPath=self.__workPath,
                                        cleanUp=False, warnings='default', verbose=self.__verbose)
                ret = sdl.load(inputPathList=inputPathList, loadType='cockroach-insert', deleteOpt='selected')
                self.assertEqual(ret, True)
        except Exception as e:
            logger.exception("Failing with %s" % str(e))
            self.fail()

    def testLoadInsertManyChemCompReference(self):

        try:
            sd, _, _ = self.__ctU.getSchemaInfo(contentType='chem_comp')
            if (self.__createFlag):
                self.__schemaCreate(schemaDefObj=sd)
            inputPathList = self.__ctU.getPathList(contentType='chem_comp')
            with Connection(cfgOb=self.__cfgOb, resourceName=self.__resourceName) as client:
                sdl = CockroachDbLoader(schemaDefObj=sd, ioObj=self.__ioObj, dbCon=client, workPath=self.__workPath,
                                        cleanUp=False, warnings='default', verbose=self.__verbose)
                ret = sdl.load(inputPathList=inputPathList, loadType='cockroach-insert-many', deleteOpt='selected')
                self.assertEqual(ret, True)
        except Exception as e:
            logger.exception("Failing with %s" % str(e))
            self.fail()

    def testLoadInsertPdbxExampleFiles(self):
        try:
            sd, _, _ = self.__ctU.getSchemaInfo(contentType='pdbx')
            if (self.__createFlag):
                self.__schemaCreate(schemaDefObj=sd)
            inputPathList = self.__ctU.getPathList(contentType='pdbx')
            with Connection(cfgOb=self.__cfgOb, resourceName=self.__resourceName) as client:
                sdl = CockroachDbLoader(schemaDefObj=sd, ioObj=self.__ioObj, dbCon=client, workPath=self.__workPath,
                                        cleanUp=False, warnings='default', verbose=self.__verbose)
                ret = sdl.load(inputPathList=inputPathList, loadType='cockroach-insert', deleteOpt='selected', tableIdSkipD=self.__tableIdSkipD)
                self.assertEqual(ret, True)
        except Exception as e:
            logger.exception("Failing with %s" % str(e))
            self.fail()

    def testLoadInsertManyPdbxExampleFiles(self):
        try:
            sd, _, _ = self.__ctU.getSchemaInfo(contentType='pdbx')
            if (self.__createFlag):
                self.__schemaCreate(schemaDefObj=sd)
            inputPathList = self.__ctU.getPathList(contentType='pdbx')
            with Connection(cfgOb=self.__cfgOb, resourceName=self.__resourceName) as client:
                sdl = CockroachDbLoader(schemaDefObj=sd, ioObj=self.__ioObj, dbCon=client, workPath=self.__workPath, cleanUp=False, warnings='default', verbose=self.__verbose)
                ret = sdl.load(inputPathList=inputPathList, loadType='cockroach-insert-many', deleteOpt='selected', tableIdSkipD=self.__tableIdSkipD)
                self.assertEqual(ret, True)
        except Exception as e:
            logger.exception("Failing with %s" % str(e))
            self.fail()

    def __schemaCreateSQL(self, schemaDefObj):
        """Test case -  create table schema using schema definition
        """
        sqlL = []
        try:
            tableIdList = schemaDefObj.getTableIdList()
            sqlGen = SqlGenAdmin(self.__verbose, serverType="CockroachDb")
            dbName = schemaDefObj.getVersionedDatabaseName()
            sqlL = sqlGen.createDatabaseSQL(dbName)
            for tableId in tableIdList:
                tableDefObj = schemaDefObj.getTable(tableId)
                sqlL.extend(sqlGen.createTableSQL(databaseName=schemaDefObj.getVersionedDatabaseName(), tableDefObj=tableDefObj))
            logger.debug("\nSchema creation SQL string\n %s\n\n" % '\n'.join(sqlL))
        except Exception as e:
            logger.exception("Failing with %s" % str(e))
            self.fail()
        return sqlL

    def __schemaCreate(self, schemaDefObj):
        """Test case -  create table schema using schema definition
        """
        ret = 0
        try:
            tableIdList = schemaDefObj.getTableIdList()
            sqlGen = SqlGenAdmin(self.__verbose, serverType="CockroachDb")
            dbName = schemaDefObj.getVersionedDatabaseName()
            sqlL = sqlGen.createDatabaseSQL(dbName)
            for tableId in tableIdList:
                tableDefObj = schemaDefObj.getTable(tableId)
                sqlL.extend(sqlGen.createTableSQL(databaseName=schemaDefObj.getVersionedDatabaseName(), tableDefObj=tableDefObj))

            logger.debug("\nSchema creation SQL string\n %s\n\n" % '\n'.join(sqlL))
            logger.info("Creating schema using database %s" % schemaDefObj.getVersionedDatabaseName())
            #
            with Connection(cfgOb=self.__cfgOb, resourceName=self.__resourceName) as client:
                crQ = CockroachDbQuery(dbcon=client, verbose=self.__verbose)
                ret = crQ.sqlCommandList(sqlCommandList=sqlL)
                # ret = crQ.sqlCommand(' '.join(sqlL))
                logger.info("Schema create command returns %r\n" % ret)
            return ret
            #
        except Exception as e:
            logger.exception("Failing with %s" % str(e))
            self.fail()

    def __schemaRemove(self, schemaDefObj):
        """Test case -  remove table schema using schema definition
        """
        ret = 0
        try:
            dbName = schemaDefObj.getVersionedDatabaseName()
            sqlGen = SqlGenAdmin(self.__verbose, serverType="CockroachDb")
            sqlL = sqlGen.removeDatabaseSQL(dbName)
            logger.debug("Schema Remove SQL string\n %s" % '\n'.join(sqlL))
            with Connection(cfgOb=self.__cfgOb, resourceName=self.__resourceName) as client:
                crQ = CockroachDbQuery(dbcon=client, verbose=self.__verbose)
                ret = crQ.sqlCommandList(sqlCommandList=sqlL)
                # ret = crQ.sqlCommand(' '.join(sqlL))
                logger.debug("Schema remove command returns %r\n" % ret)
            return ret
            #
        except Exception as e:
            logger.exception("Failing with %s" % str(e))
            self.fail()


def createConnectionSuite():
    suiteSelect = unittest.TestSuite()
    suiteSelect.addTest(CockroachDbLoaderCockroachDbTests("testConnection"))
    # suiteSelect.addTest(CockroachDbLoaderCockroachDbTests("testClusterConnections"))
    return suiteSelect


def removeSchemaSuite():
    suiteSelect = unittest.TestSuite()
    suiteSelect.addTest(CockroachDbLoaderCockroachDbTests("testSchemaRemove"))
    return suiteSelect


def createSchemaSuite():
    suiteSelect = unittest.TestSuite()
    suiteSelect.addTest(CockroachDbLoaderCockroachDbTests("testSchemaCreate"))
    return suiteSelect


def loadBirdReferenceSuite():
    suiteSelect = unittest.TestSuite()
    suiteSelect.addTest(CockroachDbLoaderCockroachDbTests("testLoadInsertBirdReference"))
    suiteSelect.addTest(CockroachDbLoaderCockroachDbTests("testLoadInsertManyBirdReference"))
    return suiteSelect


def loadCCReferenceSuite():
    suiteSelect = unittest.TestSuite()
    suiteSelect.addTest(CockroachDbLoaderCockroachDbTests("testLoadInsertChemCompReference"))
    suiteSelect.addTest(CockroachDbLoaderCockroachDbTests("testLoadInsertManyChemCompReference"))
    return suiteSelect


def loadPdbxSuite():
    suiteSelect = unittest.TestSuite()
    suiteSelect.addTest(CockroachDbLoaderCockroachDbTests("testLoadInsertPdbxExampleFiles"))
    suiteSelect.addTest(CockroachDbLoaderCockroachDbTests("testLoadInsertManyPdbxExampleFiles"))
    return suiteSelect


if __name__ == '__main__':
    #
    if (True):
        mySuite = createConnectionSuite()
        unittest.TextTestRunner(verbosity=2).run(mySuite)

    if (True):
        mySuite = removeSchemaSuite()
        unittest.TextTestRunner(verbosity=2).run(mySuite)

    if (True):
        mySuite = createSchemaSuite()
        unittest.TextTestRunner(verbosity=2).run(mySuite)

    if (False):
        if (True):
            mySuite = loadBirdReferenceSuite()
            unittest.TextTestRunner(verbosity=2).run(mySuite)

        if (True):
            mySuite = loadCCReferenceSuite()
            unittest.TextTestRunner(verbosity=2).run(mySuite)
    #
        if (True):
            mySuite = loadPdbxSuite()
            unittest.TextTestRunner(verbosity=2).run(mySuite)
#
