# -*- coding: utf-8 -*-

"""
***************************************************************************
    Processing.py
    ---------------------
    Date                 : August 2012
    Copyright            : (C) 2012 by Victor Olaya
    Email                : volayaf at gmail dot com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
from __future__ import print_function
from builtins import str
from builtins import object

__author__ = 'Victor Olaya'
__date__ = 'August 2012'
__copyright__ = '(C) 2012, Victor Olaya'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import os
import traceback

from qgis.PyQt.QtCore import Qt, QCoreApplication
from qgis.PyQt.QtWidgets import QApplication
from qgis.PyQt.QtGui import QCursor

from qgis.utils import iface
from qgis.core import (QgsMessageLog,
                       QgsApplication,
                       QgsMapLayer,
                       QgsProcessingProvider,
                       QgsProcessingAlgorithm,
                       QgsProcessingParameterDefinition,
                       QgsProcessingOutputVectorLayer,
                       QgsProcessingOutputRasterLayer)

import processing
from processing.script.ScriptUtils import ScriptUtils
from processing.core.ProcessingConfig import ProcessingConfig
from processing.core.GeoAlgorithm import GeoAlgorithm
from processing.gui.MessageBarProgress import MessageBarProgress
from processing.gui.RenderingStyles import RenderingStyles
from processing.gui.Postprocessing import handleAlgorithmResults
from processing.gui.AlgorithmExecutor import execute
from processing.tools import dataobjects
from processing.core.GeoAlgorithmExecutionException import GeoAlgorithmExecutionException

from processing.algs.qgis.QGISAlgorithmProvider import QGISAlgorithmProvider  # NOQA
#from processing.algs.grass7.Grass7AlgorithmProvider import Grass7AlgorithmProvider  # NOQA
#from processing.algs.gdal.GdalAlgorithmProvider import GdalAlgorithmProvider  # NOQA
#from processing.algs.saga.SagaAlgorithmProvider import SagaAlgorithmProvider  # NOQA
from processing.script.ScriptAlgorithmProvider import ScriptAlgorithmProvider  # NOQA
#from processing.preconfigured.PreconfiguredAlgorithmProvider import PreconfiguredAlgorithmProvider  # NOQA

# should be loaded last - ensures that all dependent algorithms are available when loading models
from processing.modeler.ModelerAlgorithmProvider import ModelerAlgorithmProvider  # NOQA


class Processing(object):
    BASIC_PROVIDERS = []

    @staticmethod
    def activateProvider(providerOrName, activate=True):
        provider_id = providerOrName.id() if isinstance(providerOrName, QgsProcessingProvider) else providerOrName
        provider = QgsApplication.processingRegistry().providerById(provider_id)
        try:
            provider.setActive(True)
            provider.refreshAlgorithms()
        except:
            # provider could not be activated
            QgsMessageLog.logMessage(Processing.tr('Error: Provider {0} could not be activated\n').format(provider_id),
                                     Processing.tr("Processing"))

    @staticmethod
    def initialize():
        if "model" in [p.id() for p in QgsApplication.processingRegistry().providers()]:
            return
        # Add the basic providers
        for c in QgsProcessingProvider.__subclasses__():
            p = c()
            Processing.BASIC_PROVIDERS.append(p)
            QgsApplication.processingRegistry().addProvider(p)
        # And initialize
        ProcessingConfig.initialize()
        ProcessingConfig.readSettings()
        RenderingStyles.loadStyles()

    @staticmethod
    def deinitialize():
        for p in Processing.BASIC_PROVIDERS:
            QgsApplication.processingRegistry().removeProvider(p)

        Processing.BASIC_PROVIDERS = []

    @staticmethod
    def addScripts(folder):
        Processing.initialize()
        provider = QgsApplication.processingRegistry().providerById("qgis")
        scripts = ScriptUtils.loadFromFolder(folder)
        # fix_print_with_import
        print(scripts)
        for script in scripts:
            script.allowEdit = False
            script._icon = provider._icon
        provider.externalAlgs.extend(scripts)
        provider.refreshAlgorithms()

    @staticmethod
    def removeScripts(folder):
        provider = QgsApplication.processingRegistry().providerById("qgis")
        for alg in provider.externalAlgs[::-1]:
            path = os.path.dirname(alg.descriptionFile)
            if path == folder:
                provider.externalAlgs.remove(alg)
        provider.refreshAlgorithms()

    @staticmethod
    def runAlgorithm(algOrName, parameters, onFinish=None, feedback=None, context=None):
        if isinstance(algOrName, QgsProcessingAlgorithm):
            alg = algOrName
        else:
            alg = QgsApplication.processingRegistry().createAlgorithmById(algOrName)

        if feedback is None:
            feedback = MessageBarProgress(alg.displayName() if alg else Processing.tr('Processing'))

        if alg is None:
            # fix_print_with_import
            print('Error: Algorithm not found\n')
            msg = Processing.tr('Error: Algorithm {0} not found\n').format(algOrName)
            feedback.reportError(msg)
            raise GeoAlgorithmExecutionException(msg)

        # check for any mandatory parameters which were not specified
        for param in alg.parameterDefinitions():
            if param.name() not in parameters:
                if not param.flags() & QgsProcessingParameterDefinition.FlagOptional:
                    # fix_print_with_import
                    msg = Processing.tr('Error: Missing parameter value for parameter {0}.').format(param.name())
                    print('Error: Missing parameter value for parameter %s.' % param.name())
                    feedback.reportError(msg)
                    raise GeoAlgorithmExecutionException(msg)

        if context is None:
            context = dataobjects.createContext(feedback)

        ok, msg = alg.checkParameterValues(parameters, context)
        if not ok:
            # fix_print_with_import
            print('Unable to execute algorithm\n' + str(msg))
            msg = Processing.tr('Unable to execute algorithm\n{0}').format(msg)
            feedback.reportError(msg)
            raise GeoAlgorithmExecutionException(msg)

        if not alg.validateInputCrs(parameters, context):
            print('Warning: Not all input layers use the same CRS.\n' +
                  'This can cause unexpected results.')
            feedback.pushInfo(
                Processing.tr('Warning: Not all input layers use the same CRS.\nThis can cause unexpected results.'))

        ret, results = execute(alg, parameters, context, feedback)
        if ret:
            feedback.pushInfo(
                Processing.tr('Results: {}').format(results))

            if onFinish is not None:
                onFinish(alg, context, feedback)
            else:
                # auto convert layer references in results to map layers
                for out in alg.outputDefinitions():
                    if isinstance(out, (QgsProcessingOutputVectorLayer, QgsProcessingOutputRasterLayer)):
                        result = results[out.name()]
                        if not isinstance(result, QgsMapLayer):
                            layer = context.takeResultLayer(result) # transfer layer ownership out of context
                            if layer:
                                results[out.name()] = layer # replace layer string ref with actual layer (+ownership)
        else:
            msg = Processing.tr("There were errors executing the algorithm.")
            feedback.reportError(msg)
            raise GeoAlgorithmExecutionException(msg)

        if isinstance(feedback, MessageBarProgress):
            feedback.close()
        return results

    @staticmethod
    def tr(string, context=''):
        if context == '':
            context = 'Processing'
        return QCoreApplication.translate(context, string)
