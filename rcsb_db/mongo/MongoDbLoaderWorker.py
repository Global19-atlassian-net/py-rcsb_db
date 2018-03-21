##
# File:    MongoDbLoaderWorker.py
# Author:  J. Westbrook
# Date:    14-Mar-2018
# Version: 0.001
#
# Updates:
#     20-Mar-2018 jdw  adding prdcc within chemical component collection
#     21-Mar-2018 jdw  content filtering options added from documents
##
"""
Worker methods for loading MongoDb using BIRD, CCD and PDBx/mmCIF data files
and following external schema definitions.

"""

__docformat__ = "restructuredtext en"
__author__ = "John Westbrook"
__email__ = "jwest@rcsb.rutgers.edu"
__license__ = "Apache 2.0"


import sys
import os
import time
import scandir
import pickle

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

from rcsb_db.loaders.SchemaDefDataPrep import SchemaDefDataPrep
from rcsb_db.schema.BirdSchemaDef import BirdSchemaDef
from rcsb_db.schema.ChemCompSchemaDef import ChemCompSchemaDef
from rcsb_db.schema.PdbxSchemaDef import PdbxSchemaDef
from rcsb_db.utils.MultiProcUtil import MultiProcUtil
from rcsb_db.utils.ConfigUtil import ConfigUtil

from mmcif_utils.bird.PdbxPrdIo import PdbxPrdIo
from mmcif_utils.bird.PdbxPrdCcIo import PdbxPrdCcIo
from mmcif_utils.bird.PdbxFamilyIo import PdbxFamilyIo
from mmcif_utils.chemcomp.PdbxChemCompIo import PdbxChemCompIo

from rcsb_db.mongo.ConnectionBase import ConnectionBase
from rcsb_db.mongo.MongoDbUtil import MongoDbUtil


class MongoDbLoaderWorker(object):

    def __init__(self, configPath, configName, numProc=4, chunkSize=15, fileLimit=None, verbose=False, readBackCheck=False):
        self.__verbose = verbose
        #
        # Limit the load length of each file type for testing  -  Set to None to remove -
        self.__fileLimit = fileLimit
        #
        # Controls for multiprocessing execution -
        self.__numProc = numProc
        self.__chunkSize = chunkSize
        #
        self.__cu = ConfigUtil(configPath=configPath, sectionName=configName)
        self.__birdCachePath = self.__cu.get('BIRD_REPO_PATH')
        self.__birdFamilyCachePath = self.__cu.get('BIRD_FAMILY_REPO_PATH')
        self.__prdCcCachePath = self.__cu.get('BIRD_CHEM_COMP_REPO_PATH')
        self.__ccCachePath = self.__cu.get('CHEM_COMP_REPO_PATH')
        self.__pdbxFileCache = self.__cu.get('RCSB_PDBX_SANBOX_PATH')
        self.__pdbxLoadListPath = self.__cu.get('PDBX_LOAD_LIST_PATH')
        self.__pdbxTableIdExcludeList = str(self.__cu.get('PDBX_EXCLUDE_TABLES', defaultValue="")).split(',')
        self.__readBackCheck = readBackCheck
        #
        self.__prefD = self.__assignPreferences(self.__cu)

    def loadContentType(self, contentType, styleType='rowwise_by_name', contentSelectors=None):
        """  Driver method for loading MongoDb content -

            contentType:  one of 'bird','bird-family','chem-comp','pdbx'
            styleType:    one of 'rowwise_by_name', 'columnwise_by_name', 'rowwise_no_name', 'rowwise_by_name_with_cardinality'

        """
        try:
            startTime = self.__begin(message="loading operation")
            sd, dbName, collectionName, inputPathList, tableIdExcludeList = self.__getLoadInfo(contentType)
            #
            optD = {}
            optD['sd'] = sd
            optD['dbName'] = dbName
            optD['collectionName'] = collectionName
            optD['styleType'] = styleType
            optD['tableIdExcludeList'] = tableIdExcludeList
            optD['prefD'] = self.__prefD
            optD['readBackCheck'] = self.__readBackCheck
            optD['logSize'] = self.__verbose
            optD['contentSelectors'] = contentSelectors
            #
            self.__removeCollection(dbName, collectionName, self.__prefD)
            self.__createCollection(dbName, collectionName, self.__prefD)
            #
            numProc = self.__numProc
            chunkSize = self.__chunkSize if self.__chunkSize < len(inputPathList) else 0
            #
            mpu = MultiProcUtil(verbose=True)
            mpu.setOptions(optionsD=optD)
            mpu.set(workerObj=self, workerMethod="loadWorker")
            ok, failList, retLists, diagList = mpu.runMulti(dataList=inputPathList, numProc=numProc, numResults=1, chunkSize=chunkSize)
            logger.info("Failing path list %r" % failList)
            logger.info("Input path list length %d failed list length %d" % (len(inputPathList), len(failList)))
            self.__end(startTime, "loading operation with status " + str(ok))

            #
            return ok
        except Exception as e:
            logger.exception("Failing with %s" % str(e))

        return False

    def loadWorker(self, dataList, procName, optionsD, workingDir):
        """ Multi-proc worker method for MongoDb loading -
        """
        try:
            startTime = self.__begin(message=procName)
            sd = optionsD['sd']
            styleType = optionsD['styleType']
            tableIdExcludeList = optionsD['tableIdExcludeList']
            dbName = optionsD['dbName']
            collectionName = optionsD['collectionName']
            prefD = optionsD['prefD']
            readBackCheck = optionsD['readBackCheck']
            logSize = 'logSize' in optionsD and optionsD['logSize']
            contentSelectors = optionsD['contentSelectors']

            sdp = SchemaDefDataPrep(schemaDefObj=sd, verbose=self.__verbose)
            sdp.setTableIdExcludeList(tableIdExcludeList)
            fType = "drop-empty-attributes|drop-empty-tables|skip-max-width|assign-dates|convert-iterables"
            if styleType in ["columnwise_by_name", "rowwise_no_name"]:
                fType = "drop-empty-tables|skip-max-width|assign-dates|convert-iterables"
            tableDataDictList, containerNameList, rejectList = sdp.fetchDocuments(dataList, styleType=styleType, filterType=fType, contentSelectors=contentSelectors)
            #
            if logSize:
                maxDocumentMegaBytes = -1
                for tD, cN in zip(tableDataDictList, containerNameList):
                    documentMegaBytes = float(sys.getsizeof(pickle.dumps(tD, protocol=0))) / 1000000.0
                    logger.debug("Document %s  %.4f MB" % (cN, documentMegaBytes))
                    maxDocumentMegaBytes = max(maxDocumentMegaBytes, documentMegaBytes)
                    if documentMegaBytes > 15.8:
                        logger.info("Large document %s  %.4f MB" % (cN, documentMegaBytes))
                logger.info("Maximum document size loaded %.4f MB" % maxDocumentMegaBytes)
            #
            #  Get the tableId.attId holding the natural document Id
            docIdD = {}
            docIdD['tableName'], docIdD['attributeName'] = sd.getDocumentKeyAttributeName(collectionName)
            logger.debug("docIdD %r collectionName %r" % (docIdD, collectionName))

            ok, successPathList = self.__loadDocuments(dbName, collectionName, prefD, tableDataDictList, docIdD, successKey='__INPUT_PATH__', readBackCheck=readBackCheck)
            #
            logger.info("%s SuccessList length = %d  rejected %d" % (procName, len(successPathList), len(rejectList)))
            successPathList.extend(rejectList)
            successPathList = list(set(successPathList))
            self.__end(startTime, procName + " with status " + str(ok))

            return successPathList, [], []

        except Exception as e:
            logger.error("Failing with dataList %r" % dataList)
            logger.exception("Failing with %s" % str(e))

        return [], [], []

    # -------------- -------------- -------------- -------------- -------------- -------------- --------------
    #                                        ---  Supporting code follows ---
    #

    def __assignPreferences(self, cfgObj, dbType="mongodb"):
        dbUserId = None
        dbHost = None
        dbUserPwd = None
        dbName = None
        dbAdminDb = None
        if dbType == 'mongodb':
            dbUserId = cfgObj.get("MONGO_DB_USER_NAME")
            dbUserPwd = cfgObj.get("MONGO_DB_PASSWORD")
            dbName = cfgObj.get("MONGO_DB_NAME")
            dbHost = cfgObj.get("MONGO_DB_HOST")
            dbPort = cfgObj.get("MONGO_DB_PORT")
            dbAdminDb = cfgObj.get("MONGO_DB_ADMIN_DB_NAME")
        else:
            pass

        prefD = {"DB_HOST": dbHost, 'DB_USER': dbUserId, 'DB_PW': dbUserPwd, 'DB_NAME': dbName, "DB_PORT": dbPort, 'DB_ADMIN_DB_NAME': dbAdminDb}
        return prefD

    def __begin(self, message=""):
        startTime = time.time()
        ts = time.strftime("%Y %m %d %H:%M:%S", time.localtime())
        logger.debug("Running application version %s" % __version__)
        logger.debug("Starting %s at %s" % (message, ts))
        return startTime

    def __end(self, startTime, message=""):
        endTime = time.time()
        ts = time.strftime("%Y %m %d %H:%M:%S", time.localtime())
        delta = endTime - startTime
        logger.info("Completed %s at %s (%.4f seconds)\n" % (message, ts, delta))

    def __open(self, prefD):
        cObj = ConnectionBase()
        cObj.setPreferences(prefD)
        ok = cObj.openConnection()
        if ok:
            return cObj
        else:
            return None

    def __close(self, cObj):
        if cObj is not None:
            cObj.closeConnection()
            return True
        else:
            return False

    def __getClientConnection(self, cObj):
        return cObj.getClientConnection()

    def __createCollection(self, dbName, collectionName, prefD):
        """Create database and collection -
        """
        try:
            cObj = self.__open(prefD)
            client = self.__getClientConnection(cObj)
            mg = MongoDbUtil(client)
            ok = mg.createCollection(dbName, collectionName)
            ok = mg.databaseExists(dbName)
            ok = mg.collectionExists(dbName, collectionName)
            ok = self.__close(cObj)
            return ok
            #
        except Exception as e:
            logger.exception("Failing with %s" % str(e))
        return False

    def __removeCollection(self, dbName, collectionName, prefD):
        """Drop collection within database

        """
        try:
            cObj = self.__open(prefD)
            client = self.__getClientConnection(cObj)
            mg = MongoDbUtil(client)
            #
            logger.debug("Databases = %r" % mg.getDatabaseNames())
            logger.debug("Collections = %r" % mg.getCollectionNames(dbName))
            ok = mg.dropCollection(dbName, collectionName)
            logger.debug("Databases = %r" % mg.getDatabaseNames())
            logger.debug("Collections = %r" % mg.getCollectionNames(dbName))
            ok = mg.collectionExists(dbName, collectionName)
            logger.debug("Collections = %r" % mg.getCollectionNames(dbName))
            ok = self.__close(cObj)
            return ok
        except Exception as e:
            logger.exception("Failing with %s" % str(e))
        return False

    def __loadDocuments(self, dbName, collectionName, prefD, dList, docIdD, successKey=None, readBackCheck=False):
        #
        # Create index mapping documents in input list to the natural document identifier.
        indD = {}
        try:
            for ii, d in enumerate(dList):
                tn = docIdD['tableName']
                an = docIdD['attributeName']
                dId = d[tn][an]
                indD[dId] = ii
        except Exception as e:
            logger.exception("Failing with %s" % str(e))

        try:
            cObj = self.__open(prefD)
            client = self.__getClientConnection(cObj)
            mg = MongoDbUtil(client)
            #
            rIdL = mg.insertList(dbName, collectionName, dList)
            #
            #  If there is a failure then determine the success list -
            #
            successList = [d[successKey] for d in dList]
            if len(rIdL) != len(dList):
                successList = []
                for rId in rIdL:
                    rObj = mg.fetchOne(dbName, collectionName, '_id', rId)
                    docId = rObj[docIdD['tableName']][docIdD['attributeName']]
                    jj = indD[docId]
                    successList.append(dList[jj][successKey])
            #
            if readBackCheck:
                #
                # Note that objects in dList are mutated by additional key '_id' that is added on insert -
                #
                rbStatus = True
                for ii, rId in enumerate(rIdL):
                    rObj = mg.fetchOne(dbName, collectionName, '_id', rId)
                    docId = rObj[docIdD['tableName']][docIdD['attributeName']]
                    jj = indD[docId]
                    if (rObj != dList[jj]):
                        rbStatus = False
                        break
            #
            ok = self.__close(cObj)
            if readBackCheck and not rbStatus:
                return False, successList
            #
            return len(rIdL) == len(dList), successList
        except Exception as e:
            logger.exception("Failing with %s" % str(e))
        return False, []

    def __getLoadInfo(self, contentType):
        sd = None
        dbName = None
        collectionName = None
        inputPathList = []
        tableIdExcludeList = []
        try:
            if contentType == "bird":
                sd = BirdSchemaDef(convertNames=True)
                dbName = sd.getDatabaseName()
                collectionName = sd.getVersionedDatabaseName()
                inputPathList = self.__getPrdPathList()
            elif contentType == "bird-family":
                sd = BirdSchemaDef(convertNames=True)
                dbName = sd.getDatabaseName()
                collectionName = "family_v4_0_1"
                inputPathList = self.__getPrdFamilyPathList()
            elif contentType == 'chem-comp':
                sd = ChemCompSchemaDef(convertNames=True)
                dbName = sd.getDatabaseName()
                collectionName = sd.getVersionedDatabaseName()
                inputPathList = self.__getChemCompPathList()
            elif contentType == 'bird-chem-comp':
                sd = ChemCompSchemaDef(convertNames=True)
                dbName = sd.getDatabaseName()
                collectionName = "bird_chem_comp_v4_0_1"
                inputPathList = self.__getPrdCCPathList()
            elif contentType == 'pdbx':
                sd = PdbxSchemaDef(convertNames=True)
                dbName = sd.getDatabaseName()
                collectionName = sd.getVersionedDatabaseName()
                # inputPathList = self.__makePdbxPathListInLine(cachePath=self.__pdbxFileCache)
                inputPathList = self.__getPdbxPathList(self.__pdbxLoadListPath, cachePath=self.__pdbxFileCache)
                tableIdExcludeList = self.__pdbxTableIdExcludeList
            else:
                logger.warning("Unsupported contentType %s" % contentType)
        except Exception as e:
            logger.exception("Failing with %s" % str(e))

        if self.__fileLimit:
            inputPathList = inputPathList[:self.__fileLimit]

        return sd, dbName, collectionName, inputPathList, tableIdExcludeList


# -------------

    def __getPrdPathList(self):
        """Get the path list of PRD definitions in the CVS repository.
        """
        try:
            refIo = PdbxPrdIo(verbose=self.__verbose)
            refIo.setCachePath(self.__birdCachePath)
            loadPathList = refIo.makeDefinitionPathList()
            logger.debug("Length of BIRD file path list %d (limit %r)" % (len(loadPathList), self.__fileLimit))
            if self.__fileLimit:
                return loadPathList[:self.__fileLimit]
            else:
                return loadPathList
        except Exception as e:
            logger.exception("Failing with %s" % str(e))

    def __getPrdFamilyPathList(self):
        """Get the path list of PRD Family definitions in the CVS repository.
        """
        try:
            refIo = PdbxFamilyIo(verbose=self.__verbose)
            refIo.setCachePath(self.__birdFamilyCachePath)
            loadPathList = refIo.makeDefinitionPathList()
            logger.debug("Length of BIRD FAMILY file path list %d (limit %r)" % (len(loadPathList), self.__fileLimit))
            if self.__fileLimit:
                return loadPathList[:self.__fileLimit]
            else:
                return loadPathList
        except Exception as e:
            logger.exception("Failing with %s" % str(e))

    def __getChemCompPathList(self):
        """Get the path list of chemical component definitions in the repository.
        """
        try:
            refIo = PdbxChemCompIo(verbose=self.__verbose)
            refIo.setCachePath(self.__ccCachePath)
            loadPathList = refIo.makeComponentPathList()
            logger.debug("Length of CCD file path list %d (limit %r)" % (len(loadPathList), self.__fileLimit))
            if self.__fileLimit:
                return loadPathList[:self.__fileLimit]
            else:
                return loadPathList
        except Exception as e:
            logger.exception("Failing with %s" % str(e))

    def __getPrdCCPathList(self):
        """Get the path list of BIRD PRD CC definitions in therepository.
        """
        try:
            refIo = PdbxPrdCcIo(verbose=self.__verbose)
            refIo.setCachePath(self.__prdCcCachePath)
            loadPathList = refIo.makeDefinitionPathList()
            logger.debug("Length of PRD CC file path list %d (limit %r)" % (len(loadPathList), self.__fileLimit))
            if self.__fileLimit:
                return loadPathList[:self.__fileLimit]
            else:
                return loadPathList
        except Exception as e:
            logger.exception("Failing with %s" % str(e))

    def __getPdbxPathList(self, fileListPath, cachePath):
        pathList = self.__readPathList(fileListPath)
        if len(pathList) < 1:
            ok = self.__makePdbxPathList(fileListPath, cachePath)
            if ok:
                pathList = self.__readPathList(fileListPath)
            else:
                pathList = []
        return pathList

    def __readPathList(self, fileListPath):
        pathList = []
        try:
            with open(fileListPath, 'r') as ifh:
                for line in ifh:
                    pth = str(line[:-1]).strip()
                    pathList.append(pth)
        except Exception as e:
            pass
        logger.debug("Reading path list length %d" % len(pathList))
        return pathList

    def __makePdbxPathList(self, fileListPath, cachePath=None):
        """ Return the list of pdbx file paths in the current repository and store this

        """
        try:
            with open(fileListPath, 'w') as ofh:
                for root, dirs, files in scandir.walk(cachePath, topdown=False):
                    if "REMOVE" in root:
                        continue
                    for name in files:
                        if name.endswith(".cif") and len(name) == 8:
                            ofh.write("%s\n" % os.path.join(root, name))
                #
            return True
        except Exception as e:
            logger.exception("Failing with %s" % str(e))

        return False

    def __makePdbxPathListInLine(self, cachePath=None):
        """ Return the list of pdbx file paths in the current repository.
        """
        pathList = []
        try:
            for root, dirs, files in scandir.walk(cachePath, topdown=False):
                if "REMOVE" in root:
                    continue
                for name in files:
                    if name.endswith(".cif") and len(name) == 8:
                        pathList.append(os.path.join(root, name))

            logger.debug("\nFound %d files in %s\n" % (len(pathList), cachePath))
        except Exception as e:
            logger.exception("Failing with %s" % str(e))

        return pathList
