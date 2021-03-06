# -*- coding: utf-8 -*-

"""
***************************************************************************
    FieldsCalculator.py
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

__author__ = 'Victor Olaya'
__date__ = 'August 2012'
__copyright__ = '(C) 2012, Victor Olaya'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

from qgis.PyQt.QtCore import QVariant
from qgis.core import (QgsExpression,
                       QgsExpressionContext,
                       QgsExpressionContextUtils,
                       QgsFeature,
                       QgsFeatureSink,
                       QgsField,
                       QgsDistanceArea,
                       QgsProject,
                       QgsApplication,
                       QgsProcessingUtils)
from processing.algs.qgis.QgisAlgorithm import QgisAlgorithm
from processing.core.GeoAlgorithmExecutionException import GeoAlgorithmExecutionException
from processing.core.parameters import ParameterVector
from processing.core.parameters import ParameterString
from processing.core.parameters import ParameterNumber
from processing.core.parameters import ParameterBoolean
from processing.core.parameters import ParameterSelection
from processing.core.outputs import OutputVector

from .ui.FieldsCalculatorDialog import FieldsCalculatorDialog


class FieldsCalculator(QgisAlgorithm):

    INPUT_LAYER = 'INPUT_LAYER'
    NEW_FIELD = 'NEW_FIELD'
    FIELD_NAME = 'FIELD_NAME'
    FIELD_TYPE = 'FIELD_TYPE'
    FIELD_LENGTH = 'FIELD_LENGTH'
    FIELD_PRECISION = 'FIELD_PRECISION'
    FORMULA = 'FORMULA'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    TYPES = [QVariant.Double, QVariant.Int, QVariant.String, QVariant.Date]

    def group(self):
        return self.tr('Vector table tools')

    def __init__(self):
        super().__init__()

    def initAlgorithm(self, config=None):
        self.type_names = [self.tr('Float'),
                           self.tr('Integer'),
                           self.tr('String'),
                           self.tr('Date')]

        self.addParameter(ParameterVector(self.INPUT_LAYER,
                                          self.tr('Input layer')))
        self.addParameter(ParameterString(self.FIELD_NAME,
                                          self.tr('Result field name')))
        self.addParameter(ParameterSelection(self.FIELD_TYPE,
                                             self.tr('Field type'), self.type_names))
        self.addParameter(ParameterNumber(self.FIELD_LENGTH,
                                          self.tr('Field length'), 1, 255, 10))
        self.addParameter(ParameterNumber(self.FIELD_PRECISION,
                                          self.tr('Field precision'), 0, 15, 3))
        self.addParameter(ParameterBoolean(self.NEW_FIELD,
                                           self.tr('Create new field'), True))
        self.addParameter(ParameterString(self.FORMULA, self.tr('Formula')))
        self.addOutput(OutputVector(self.OUTPUT_LAYER, self.tr('Calculated')))

    def name(self):
        return 'fieldcalculator'

    def displayName(self):
        return self.tr('Field calculator')

    def processAlgorithm(self, parameters, context, feedback):
        layer = QgsProcessingUtils.mapLayerFromString(self.getParameterValue(self.INPUT_LAYER), context)
        fieldName = self.getParameterValue(self.FIELD_NAME)
        fieldType = self.TYPES[self.getParameterValue(self.FIELD_TYPE)]
        width = self.getParameterValue(self.FIELD_LENGTH)
        precision = self.getParameterValue(self.FIELD_PRECISION)
        newField = self.getParameterValue(self.NEW_FIELD)
        formula = self.getParameterValue(self.FORMULA)

        output = self.getOutputFromName(self.OUTPUT_LAYER)

        fields = layer.fields()
        if newField:
            fields.append(QgsField(fieldName, fieldType, '', width, precision))

        writer = output.getVectorWriter(fields, layer.wkbType(), layer.crs(), context)

        exp = QgsExpression(formula)

        da = QgsDistanceArea()
        da.setSourceCrs(layer.crs())
        da.setEllipsoid(QgsProject.instance().ellipsoid())
        exp.setGeomCalculator(da)
        exp.setDistanceUnits(QgsProject.instance().distanceUnits())
        exp.setAreaUnits(QgsProject.instance().areaUnits())

        exp_context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(layer))

        if not exp.prepare(exp_context):
            raise GeoAlgorithmExecutionException(
                self.tr('Evaluation error: {0}').format(exp.evalErrorString()))

        outFeature = QgsFeature()
        outFeature.initAttributes(len(fields))
        outFeature.setFields(fields)

        error = ''
        calculationSuccess = True

        features = QgsProcessingUtils.getFeatures(layer, context)
        total = 100.0 / layer.featureCount() if layer.featureCount() else 0

        rownum = 1
        for current, f in enumerate(features):
            rownum = current + 1
            exp_context.setFeature(f)
            exp_context.lastScope().setVariable("row_number", rownum)
            value = exp.evaluate(exp_context)
            if exp.hasEvalError():
                calculationSuccess = False
                error = exp.evalErrorString()
                break
            else:
                outFeature.setGeometry(f.geometry())
                for fld in f.fields():
                    outFeature[fld.name()] = f[fld.name()]
                outFeature[fieldName] = value
                writer.addFeature(outFeature, QgsFeatureSink.FastInsert)

            feedback.setProgress(int(current * total))
        del writer

        if not calculationSuccess:
            raise GeoAlgorithmExecutionException(
                self.tr('An error occurred while evaluating the calculation '
                        'string:\n{0}').format(error))

    def checkParameterValues(self, parameters, context):
        newField = self.getParameterValue(self.NEW_FIELD)
        fieldName = self.getParameterValue(self.FIELD_NAME).strip()
        if newField and len(fieldName) == 0:
            return self.tr('Field name is not set. Please enter a field name')
        return super(FieldsCalculator, self).checkParameterValues(parameters, context)

    def createCustomParametersWidget(self, parent):
        return FieldsCalculatorDialog(self)
