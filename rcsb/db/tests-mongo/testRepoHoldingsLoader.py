##
# File:    RepoHoldingsLoaderTests.py
# Author:  J. Westbrook
# Date:    13-Jul-2018
# Version: 0.001
#
# Updates:
# 14-Jul-2018 jdw add configuration options
#  7-Oct-2018 jdw add schema validation to the underlying load processing
##
"""
Tests for loading repository holdings information.

"""

__docformat__ = "restructuredtext en"
__author__ = "John Westbrook"
__email__ = "jwest@rcsb.rutgers.edu"
__license__ = "Apache 2.0"


import logging
import os
import time
import unittest

from rcsb.db.mongo.DocumentLoader import DocumentLoader
from rcsb.db.processors.RepoHoldingsDataPrep import RepoHoldingsDataPrep
from rcsb.utils.config.ConfigUtil import ConfigUtil

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]-%(module)s.%(funcName)s: %(message)s")
logger = logging.getLogger()

HERE = os.path.abspath(os.path.dirname(__file__))
TOPDIR = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


class RepoHoldingsLoaderTests(unittest.TestCase):
    def __init__(self, methodName="runTest"):
        super(RepoHoldingsLoaderTests, self).__init__(methodName)
        self.__verbose = True

    def setUp(self):
        #
        #
        mockTopPath = os.path.join(TOPDIR, "rcsb", "mock-data")
        configPath = os.path.join(TOPDIR, "rcsb", "db", "config", "exdb-config-example.yml")
        configName = "site_info_configuration"
        self.__cfgOb = ConfigUtil(configPath=configPath, defaultSectionName=configName, mockTopPath=mockTopPath)
        # self.__cfgOb.dump()
        self.__resourceName = "MONGO_DB"
        self.__readBackCheck = True
        self.__numProc = 2
        self.__chunkSize = 10
        self.__documentLimit = None
        self.__filterType = "assign-dates"
        #
        self.__cachePath = os.path.join(TOPDIR, "CACHE")
        self.__sandboxPath = self.__cfgOb.getPath("RCSB_EXCHANGE_SANDBOX_PATH", sectionName=configName)
        # sample data set
        self.__updateId = "2019_23"
        #
        self.__startTime = time.time()
        logger.debug("Starting %s at %s", self.id(), time.strftime("%Y %m %d %H:%M:%S", time.localtime()))

    def tearDown(self):
        endTime = time.time()
        logger.debug("Completed %s at %s (%.4f seconds)", self.id(), time.strftime("%Y %m %d %H:%M:%S", time.localtime()), endTime - self.__startTime)

    def testLoadHoldings(self):
        """Test case - load legacy repository holdings and status data -

        [repository_holdings]
        DATABASE_NAME=repository_holdings
        DATABASE_VERSION_STRING=v5
        COLLECTION_HOLDINGS_UPDATE=rcsb_repository_holdings_update_entry
        COLLECTION_HOLDINGS_CURRENT=rcsb_repository_holdings_current_entry
        COLLECTION_HOLDINGS_UNRELEASED=rcsb_repository_holdings_unreleased_entry
        COLLECTION_HOLDINGS_REMOVED=rcsb_repository_holdings_removed_entry
        COLLECTION_HOLDINGS_COMBINED=rcsb_repository_holdings_combined_entry

        """
        try:
            sectionName = "repository_holdings_configuration"
            rhdp = RepoHoldingsDataPrep(cfgOb=self.__cfgOb, sandboxPath=self.__sandboxPath, cachePath=self.__cachePath, filterType=self.__filterType)
            #
            dl = DocumentLoader(
                self.__cfgOb,
                self.__cachePath,
                self.__resourceName,
                numProc=self.__numProc,
                chunkSize=self.__chunkSize,
                documentLimit=self.__documentLimit,
                verbose=self.__verbose,
                readBackCheck=self.__readBackCheck,
            )
            #
            databaseName = self.__cfgOb.get("DATABASE_NAME", sectionName=sectionName)
            # collectionVersion = self.__cfgOb.get("COLLECTION_VERSION_STRING", sectionName=sectionName)
            # addValues = {"_schema_version": collectionVersion}
            addValues = None
            #
            dList = rhdp.getHoldingsUpdateEntry(updateId=self.__updateId)
            collectionName = self.__cfgOb.get("COLLECTION_HOLDINGS_UPDATE", sectionName=sectionName)
            ok = dl.load(databaseName, collectionName, loadType="full", documentList=dList, indexAttributeList=["update_id", "entry_id"], keyNames=None, addValues=addValues)
            logger.info("Collection %r length %d load status %r", collectionName, len(dList), ok)
            self.assertTrue(ok)
            #
            dList = rhdp.getHoldingsCurrentEntry(updateId=self.__updateId)
            collectionName = self.__cfgOb.get("COLLECTION_HOLDINGS_CURRENT", sectionName=sectionName)
            ok = dl.load(databaseName, collectionName, loadType="full", documentList=dList, indexAttributeList=["update_id", "entry_id"], keyNames=None, addValues=addValues)
            logger.info("Collection %r length %d load status %r", collectionName, len(dList), ok)
            self.assertTrue(ok)

            dList = rhdp.getHoldingsUnreleasedEntry(updateId=self.__updateId)
            collectionName = self.__cfgOb.get("COLLECTION_HOLDINGS_UNRELEASED", sectionName=sectionName)
            ok = dl.load(databaseName, collectionName, loadType="full", documentList=dList, indexAttributeList=["update_id", "entry_id"], keyNames=None, addValues=addValues)
            logger.info("Collection %r length %d load status %r", collectionName, len(dList), ok)
            self.assertTrue(ok)
            #
            dList = rhdp.getHoldingsRemovedEntry(updateId=self.__updateId)
            collectionName = self.__cfgOb.get("COLLECTION_HOLDINGS_REMOVED", sectionName=sectionName)
            ok = dl.load(databaseName, collectionName, loadType="full", documentList=dList, indexAttributeList=["update_id", "entry_id"], keyNames=None, addValues=addValues)
            logger.info("Collection %r length %d load status %r", collectionName, len(dList), ok)
            self.assertTrue(ok)
            #
            dList = rhdp.getHoldingsCombinedEntry(updateId=self.__updateId)
            collectionName = self.__cfgOb.get("COLLECTION_HOLDINGS_COMBINED", sectionName=sectionName)
            ok = dl.load(databaseName, collectionName, loadType="full", documentList=dList, indexAttributeList=["update_id", "entry_id"], keyNames=None, addValues=addValues)
            logger.info("Collection %r length %d load status %r", collectionName, len(dList), ok)
            self.assertTrue(ok)
            #
        except Exception as e:
            logger.exception("Failing with %s", str(e))
            self.fail()


def holdingsLoadSuite():
    suiteSelect = unittest.TestSuite()
    suiteSelect.addTest(RepoHoldingsLoaderTests("testLoadHoldings"))
    return suiteSelect


if __name__ == "__main__":
    mySuite = holdingsLoadSuite()
    unittest.TextTestRunner(verbosity=2).run(mySuite)
