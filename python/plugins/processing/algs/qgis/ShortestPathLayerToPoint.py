# -*- coding: utf-8 -*-

"""
***************************************************************************
    ShortestPathLayerToPoint.py
    ---------------------
    Date                 : December 2016
    Copyright            : (C) 2016 by Alexander Bruy
    Email                : alexander dot bruy at gmail dot com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

__author__ = 'Alexander Bruy'
__date__ = 'December 2016'
__copyright__ = '(C) 2016, Alexander Bruy'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import os
from collections import OrderedDict

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QIcon

from qgis.core import (QgsWkbTypes,
                       QgsUnitTypes,
                       QgsFeature,
                       QgsFeatureSink,
                       QgsGeometry,
                       QgsPointXY,
                       QgsFields,
                       QgsField,
                       QgsFeatureRequest,
                       QgsMessageLog,
                       QgsProcessingParameterDefinition,
                       QgsProcessingUtils)
from qgis.analysis import (QgsVectorLayerDirector,
                           QgsNetworkDistanceStrategy,
                           QgsNetworkSpeedStrategy,
                           QgsGraphBuilder,
                           QgsGraphAnalyzer
                           )
from qgis.utils import iface

from processing.algs.qgis.QgisAlgorithm import QgisAlgorithm
from processing.core.parameters import (ParameterVector,
                                        ParameterPoint,
                                        ParameterNumber,
                                        ParameterString,
                                        ParameterTableField,
                                        ParameterSelection
                                        )
from processing.core.outputs import OutputVector
from processing.tools import dataobjects

pluginPath = os.path.split(os.path.split(os.path.dirname(__file__))[0])[0]


class ShortestPathLayerToPoint(QgisAlgorithm):

    INPUT_VECTOR = 'INPUT_VECTOR'
    START_POINTS = 'START_POINT'
    END_POINT = 'END_POINT'
    STRATEGY = 'STRATEGY'
    DIRECTION_FIELD = 'DIRECTION_FIELD'
    VALUE_FORWARD = 'VALUE_FORWARD'
    VALUE_BACKWARD = 'VALUE_BACKWARD'
    VALUE_BOTH = 'VALUE_BOTH'
    DEFAULT_DIRECTION = 'DEFAULT_DIRECTION'
    SPEED_FIELD = 'SPEED_FIELD'
    DEFAULT_SPEED = 'DEFAULT_SPEED'
    TOLERANCE = 'TOLERANCE'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'images', 'networkanalysis.svg'))

    def group(self):
        return self.tr('Network analysis')

    def __init__(self):
        super().__init__()

    def initAlgorithm(self, config=None):
        self.DIRECTIONS = OrderedDict([
            (self.tr('Forward direction'), QgsVectorLayerDirector.DirectionForward),
            (self.tr('Backward direction'), QgsVectorLayerDirector.DirectionForward),
            (self.tr('Both directions'), QgsVectorLayerDirector.DirectionForward)])

        self.STRATEGIES = [self.tr('Shortest'),
                           self.tr('Fastest')
                           ]

        self.addParameter(ParameterVector(self.INPUT_VECTOR,
                                          self.tr('Vector layer representing network'),
                                          [dataobjects.TYPE_VECTOR_LINE]))
        self.addParameter(ParameterVector(self.START_POINTS,
                                          self.tr('Vector layer with start points'),
                                          [dataobjects.TYPE_VECTOR_POINT]))
        self.addParameter(ParameterPoint(self.END_POINT,
                                         self.tr('End point')))
        self.addParameter(ParameterSelection(self.STRATEGY,
                                             self.tr('Path type to calculate'),
                                             self.STRATEGIES,
                                             default=0))

        params = []
        params.append(ParameterTableField(self.DIRECTION_FIELD,
                                          self.tr('Direction field'),
                                          self.INPUT_VECTOR,
                                          optional=True))
        params.append(ParameterString(self.VALUE_FORWARD,
                                      self.tr('Value for forward direction'),
                                      '',
                                      optional=True))
        params.append(ParameterString(self.VALUE_BACKWARD,
                                      self.tr('Value for backward direction'),
                                      '',
                                      optional=True))
        params.append(ParameterString(self.VALUE_BOTH,
                                      self.tr('Value for both directions'),
                                      '',
                                      optional=True))
        params.append(ParameterSelection(self.DEFAULT_DIRECTION,
                                         self.tr('Default direction'),
                                         list(self.DIRECTIONS.keys()),
                                         default=2))
        params.append(ParameterTableField(self.SPEED_FIELD,
                                          self.tr('Speed field'),
                                          self.INPUT_VECTOR,
                                          optional=True))
        params.append(ParameterNumber(self.DEFAULT_SPEED,
                                      self.tr('Default speed (km/h)'),
                                      0.0, 99999999.999999, 5.0))
        params.append(ParameterNumber(self.TOLERANCE,
                                      self.tr('Topology tolerance'),
                                      0.0, 99999999.999999, 0.0))

        for p in params:
            p.setFlags(p.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
            self.addParameter(p)

        self.addOutput(OutputVector(self.OUTPUT_LAYER,
                                    self.tr('Shortest path'),
                                    datatype=[dataobjects.TYPE_VECTOR_LINE]))

    def name(self):
        return 'shortestpathlayertopoint'

    def displayName(self):
        return self.tr('Shortest path (layer to point)')

    def processAlgorithm(self, parameters, context, feedback):
        layer = QgsProcessingUtils.mapLayerFromString(self.getParameterValue(self.INPUT_VECTOR), context)
        startPoints = QgsProcessingUtils.mapLayerFromString(self.getParameterValue(self.START_POINTS), context)
        endPoint = self.getParameterValue(self.END_POINT)
        strategy = self.getParameterValue(self.STRATEGY)

        directionFieldName = self.getParameterValue(self.DIRECTION_FIELD)
        forwardValue = self.getParameterValue(self.VALUE_FORWARD)
        backwardValue = self.getParameterValue(self.VALUE_BACKWARD)
        bothValue = self.getParameterValue(self.VALUE_BOTH)
        defaultDirection = self.getParameterValue(self.DEFAULT_DIRECTION)
        bothValue = self.getParameterValue(self.VALUE_BOTH)
        defaultDirection = self.getParameterValue(self.DEFAULT_DIRECTION)
        speedFieldName = self.getParameterValue(self.SPEED_FIELD)
        defaultSpeed = self.getParameterValue(self.DEFAULT_SPEED)
        tolerance = self.getParameterValue(self.TOLERANCE)

        fields = QgsFields()
        fields.append(QgsField('start', QVariant.String, '', 254, 0))
        fields.append(QgsField('end', QVariant.String, '', 254, 0))
        fields.append(QgsField('cost', QVariant.Double, '', 20, 7))

        feat = QgsFeature()
        feat.setFields(fields)

        writer = self.getOutputFromName(
            self.OUTPUT_LAYER).getVectorWriter(fields, QgsWkbTypes.LineString, layer.crs(), context)

        tmp = endPoint.split(',')
        endPoint = QgsPointXY(float(tmp[0]), float(tmp[1]))

        directionField = -1
        if directionFieldName is not None:
            directionField = layer.fields().lookupField(directionFieldName)
        speedField = -1
        if speedFieldName is not None:
            speedField = layer.fields().lookupField(speedFieldName)

        director = QgsVectorLayerDirector(layer,
                                          directionField,
                                          forwardValue,
                                          backwardValue,
                                          bothValue,
                                          defaultDirection)

        distUnit = iface.mapCanvas().mapSettings().destinationCrs().mapUnits()
        multiplier = QgsUnitTypes.fromUnitToUnitFactor(distUnit, QgsUnitTypes.DistanceMeters)
        if strategy == 0:
            strategy = QgsNetworkDistanceStrategy()
        else:
            strategy = QgsNetworkSpeedStrategy(speedField,
                                               defaultSpeed,
                                               multiplier * 1000.0 / 3600.0)
            multiplier = 3600

        director.addStrategy(strategy)
        builder = QgsGraphBuilder(iface.mapCanvas().mapSettings().destinationCrs(),
                                  True,
                                  tolerance)

        feedback.pushInfo(self.tr('Loading start points...'))
        request = QgsFeatureRequest()
        request.setFlags(request.flags() ^ QgsFeatureRequest.SubsetOfAttributes)
        features = QgsProcessingUtils.getFeatures(startPoints, context, request)
        count = QgsProcessingUtils.featureCount(startPoints, context)

        points = [endPoint]
        for f in features:
            points.append(f.geometry().asPoint())

        feedback.pushInfo(self.tr('Building graph...'))
        snappedPoints = director.makeGraph(builder, points)

        feedback.pushInfo(self.tr('Calculating shortest paths...'))
        graph = builder.graph()

        idxEnd = graph.findVertex(snappedPoints[0])
        route = []

        total = 100.0 / count if count else 1
        for i in range(1, count + 1):
            idxStart = graph.findVertex(snappedPoints[i])
            tree, cost = QgsGraphAnalyzer.dijkstra(graph, idxStart, 0)

            if tree[idxEnd] == -1:
                msg = self.tr('There is no route from start point ({}) to end point ({}).'.format(points[i].toString(), endPoint.toString()))
                feedback.setProgressText(msg)
                QgsMessageLog.logMessage(msg, self.tr('Processing'), QgsMessageLog.WARNING)
                continue

            cost = 0.0
            current = idxEnd
            while current != idxStart:
                cost += graph.edge(tree[current]).cost(0)
                route.append(graph.vertex(graph.edge(tree[current]).inVertex()).point())
                current = graph.edge(tree[current]).outVertex()

            route.append(snappedPoints[i])
            route.reverse()

            geom = QgsGeometry.fromPolyline(route)
            feat.setGeometry(geom)
            feat['start'] = points[i].toString()
            feat['end'] = endPoint.toString()
            feat['cost'] = cost / multiplier
            writer.addFeature(feat, QgsFeatureSink.FastInsert)

            route[:] = []

            feedback.setProgress(int(i * total))

        del writer
