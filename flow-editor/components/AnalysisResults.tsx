/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
'use client';

import React, { useState } from 'react';
import * as Icons from 'lucide-react';
import { BatchAnalysisResult } from '@/lib/apiClient';

interface AnalysisResultsProps {
  results: BatchAnalysisResult;
  portfolioId: string;
  onClose: () => void;
}

export default function AnalysisResults({
  results,
  portfolioId,
  onClose,
}: AnalysisResultsProps) {
  const [activeTab, setActiveTab] = useState<string>('en16798');

  const tabs = [
    { id: 'en16798', label: 'EN 16798', icon: Icons.CheckCircle2 },
    { id: 'tail', label: 'TAIL', icon: Icons.Activity },
    { id: 'br18', label: 'BR18', icon: Icons.Shield },
    { id: 'occupancy', label: 'Occupancy', icon: Icons.Users },
    { id: 'ventilation', label: 'Ventilation', icon: Icons.Wind },
    { id: 'rc_thermal', label: 'RC Thermal', icon: Icons.Thermometer },
    { id: 'epc', label: 'EPC', icon: Icons.Award },
  ];

  const renderEN16798Results = () => {
    if (!results.results.en16798) return <div>No EN 16798 results available</div>;

    return (
      <div className="space-y-4">
        {Object.entries(results.results.en16798).map(([roomId, categories]) => (
          <div key={roomId} className="border rounded-lg p-4">
            <h4 className="font-semibold text-lg mb-3">{roomId}</h4>
            <div className="grid grid-cols-2 gap-3">
              {Object.entries(categories).map(([category, data]) => (
                <div key={category} className="bg-gray-50 p-3 rounded">
                  <div className="font-medium text-sm mb-1">{category}</div>
                  <div className="text-2xl font-bold text-blue-600">
                    {data.compliance_rate.toFixed(1)}%
                  </div>
                  <div className="text-xs text-gray-500">
                    {data.compliant_hours} / {data.total_hours} hours compliant
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  };

  const renderTAILResults = () => {
    if (!results.results.tail) return <div>No TAIL results available</div>;

    const getTrafficLightColor = (light: string) => {
      switch (light) {
        case 'green':
          return 'bg-green-500';
        case 'yellow':
          return 'bg-yellow-500';
        case 'red':
          return 'bg-red-500';
        default:
          return 'bg-gray-500';
      }
    };

    return (
      <div className="space-y-4">
        {Object.entries(results.results.tail).map(([roomId, parameters]) => (
          <div key={roomId} className="border rounded-lg p-4">
            <h4 className="font-semibold text-lg mb-3">{roomId}</h4>
            <div className="grid grid-cols-3 gap-3">
              {Object.entries(parameters).map(([param, data]) => (
                <div key={param} className="bg-gray-50 p-3 rounded flex items-center gap-3">
                  <div
                    className={`w-8 h-8 rounded-full ${getTrafficLightColor(data.traffic_light)}`}
                  />
                  <div>
                    <div className="font-medium text-sm">{param}</div>
                    <div className="text-xs text-gray-500">
                      {data.compliance_percentage.toFixed(1)}%
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  };

  const renderBR18Results = () => {
    if (!results.results.br18) return <div>No BR18 results available</div>;

    return (
      <div className="space-y-4">
        {Object.entries(results.results.br18).map(([roomId, result]) => (
          <div key={roomId} className="border rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h4 className="font-semibold text-lg">{roomId}</h4>
              <span
                className={`px-3 py-1 rounded-full text-sm font-medium ${
                  result.compliant
                    ? 'bg-green-100 text-green-800'
                    : 'bg-red-100 text-red-800'
                }`}
              >
                {result.compliant ? 'Compliant' : 'Non-Compliant'}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {Object.entries(result.details).map(([param, detail]) => (
                <div key={param} className="bg-gray-50 p-3 rounded">
                  <div className="font-medium text-sm mb-1">{param}</div>
                  <div className="flex items-center justify-between">
                    <span className="text-lg font-bold">{detail.value.toFixed(2)}</span>
                    <span className="text-xs text-gray-500">
                      Threshold: {detail.threshold.toFixed(2)}
                    </span>
                  </div>
                  <span
                    className={`text-xs ${detail.compliant ? 'text-green-600' : 'text-red-600'}`}
                  >
                    {detail.compliant ? '✓ Pass' : '✗ Fail'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  };

  const renderOccupancyResults = () => {
    if (!results.results.occupancy) return <div>No occupancy results available</div>;

    return (
      <div className="space-y-4">
        {Object.entries(results.results.occupancy).map(([roomId, data]) => (
          <div key={roomId} className="border rounded-lg p-4">
            <h4 className="font-semibold text-lg mb-3">{roomId}</h4>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-gray-50 p-3 rounded">
                <div className="text-sm text-gray-600 mb-1">Average Daily Occupancy</div>
                <div className="text-2xl font-bold text-purple-600">
                  {(data.average_daily_occupancy * 100).toFixed(1)}%
                </div>
              </div>
              <div className="bg-gray-50 p-3 rounded">
                <div className="text-sm text-gray-600 mb-1">Peak Hours</div>
                <div className="text-xs space-y-1">
                  {data.peak_occupancy_hours.slice(0, 5).map((hour, idx) => (
                    <div key={idx}>{hour}</div>
                  ))}
                  {data.peak_occupancy_hours.length > 5 && (
                    <div className="text-gray-400">
                      +{data.peak_occupancy_hours.length - 5} more
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  };

  const renderVentilationResults = () => {
    if (!results.results.ventilation) return <div>No ventilation results available</div>;

    return (
      <div className="space-y-4">
        {Object.entries(results.results.ventilation).map(([roomId, data]) => (
          <div key={roomId} className="border rounded-lg p-4">
            <h4 className="font-semibold text-lg mb-3">{roomId}</h4>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-gray-50 p-3 rounded">
                <div className="text-sm text-gray-600 mb-1">Ventilation Rate (ACH)</div>
                <div className="text-2xl font-bold text-cyan-600">
                  {data.ventilation_rate_ach.toFixed(2)}
                </div>
              </div>
              <div className="bg-gray-50 p-3 rounded">
                <div className="text-sm text-gray-600 mb-1">Ventilation Rate (L/s)</div>
                <div className="text-2xl font-bold text-cyan-600">
                  {data.ventilation_rate_l_s.toFixed(2)}
                </div>
              </div>
              <div className="bg-gray-50 p-3 rounded">
                <div className="text-sm text-gray-600 mb-1">CO2 Decay Rate</div>
                <div className="text-xl font-bold">{data.co2_decay_rate.toFixed(4)}</div>
              </div>
              <div className="bg-gray-50 p-3 rounded">
                <div className="text-sm text-gray-600 mb-1">Quality Score</div>
                <div className="text-xl font-bold">{(data.quality_score * 100).toFixed(1)}%</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  };

  const renderRCThermalResults = () => {
    if (!results.results.rc_thermal) return <div>No RC thermal results available</div>;

    return (
      <div className="space-y-4">
        {Object.entries(results.results.rc_thermal).map(([roomId, data]) => (
          <div key={roomId} className="border rounded-lg p-4">
            <h4 className="font-semibold text-lg mb-3">{roomId}</h4>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-gray-50 p-3 rounded">
                <div className="text-sm text-gray-600 mb-1">R-Value (Resistance)</div>
                <div className="text-2xl font-bold text-orange-600">
                  {data.r_value.toFixed(3)}
                </div>
              </div>
              <div className="bg-gray-50 p-3 rounded">
                <div className="text-sm text-gray-600 mb-1">C-Value (Capacitance)</div>
                <div className="text-2xl font-bold text-orange-600">
                  {data.c_value.toFixed(3)}
                </div>
              </div>
              <div className="bg-gray-50 p-3 rounded">
                <div className="text-sm text-gray-600 mb-1">Time Constant</div>
                <div className="text-xl font-bold">{data.time_constant_hours.toFixed(2)} hrs</div>
              </div>
              <div className="bg-gray-50 p-3 rounded">
                <div className="text-sm text-gray-600 mb-1">Thermal Mass Category</div>
                <div className="text-xl font-bold capitalize">{data.thermal_mass_category}</div>
              </div>
              <div className="bg-gray-50 p-3 rounded col-span-2">
                <div className="text-sm text-gray-600 mb-1">Model Fit Score</div>
                <div className="text-xl font-bold">
                  {(data.model_fit_score * 100).toFixed(1)}%
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  };

  const renderEPCResults = () => {
    if (!results.results.epc) return <div>No EPC results available</div>;

    return (
      <div className="space-y-4">
        {Object.entries(results.results.epc).map(([buildingId, data]) => (
          <div key={buildingId} className="border rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h4 className="font-semibold text-lg">{buildingId}</h4>
              <span className="px-4 py-2 bg-blue-600 text-white rounded-lg text-xl font-bold">
                {data.epc_rating}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-gray-50 p-3 rounded">
                <div className="text-sm text-gray-600 mb-1">Energy Consumption</div>
                <div className="text-xl font-bold">{data.energy_consumption_kwh_m2.toFixed(1)}</div>
                <div className="text-xs text-gray-500">kWh/m²/year</div>
              </div>
              <div className="bg-gray-50 p-3 rounded">
                <div className="text-sm text-gray-600 mb-1">CO2 Emissions</div>
                <div className="text-xl font-bold">{data.co2_emissions_kg_m2.toFixed(1)}</div>
                <div className="text-xs text-gray-500">kg/m²/year</div>
              </div>
            </div>
            {data.recommendations.length > 0 && (
              <div className="mt-3">
                <div className="text-sm font-medium text-gray-700 mb-2">Recommendations:</div>
                <ul className="space-y-1">
                  {data.recommendations.map((rec, idx) => (
                    <li key={idx} className="text-sm text-gray-600 flex items-start gap-2">
                      <Icons.ArrowRight size={14} className="mt-0.5 flex-shrink-0" />
                      {rec}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ))}
      </div>
    );
  };

  const renderTabContent = () => {
    switch (activeTab) {
      case 'en16798':
        return renderEN16798Results();
      case 'tail':
        return renderTAILResults();
      case 'br18':
        return renderBR18Results();
      case 'occupancy':
        return renderOccupancyResults();
      case 'ventilation':
        return renderVentilationResults();
      case 'rc_thermal':
        return renderRCThermalResults();
      case 'epc':
        return renderEPCResults();
      default:
        return <div>Select a tab to view results</div>;
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-6xl w-full max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b">
          <div>
            <h2 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
              <Icons.BarChart3 size={24} />
              Analysis Results
            </h2>
            <p className="text-sm text-gray-500 mt-1">Portfolio ID: {portfolioId}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-full transition-colors"
          >
            <Icons.X size={24} />
          </button>
        </div>

        {/* Summary Stats */}
        <div className="px-6 py-4 bg-gray-50 border-b">
          <div className="grid grid-cols-4 gap-4">
            <div className="text-center">
              <div className="text-sm text-gray-600">Analyses Run</div>
              <div className="text-2xl font-bold text-blue-600">
                {results.analyses_run.length}
              </div>
            </div>
            <div className="text-center">
              <div className="text-sm text-gray-600">Errors</div>
              <div className="text-2xl font-bold text-red-600">{results.errors.length}</div>
            </div>
            <div className="text-center">
              <div className="text-sm text-gray-600">EN 16798</div>
              <div className="text-2xl font-bold text-green-600">
                {results.results.en16798 ? Object.keys(results.results.en16798).length : 0}
              </div>
            </div>
            <div className="text-center">
              <div className="text-sm text-gray-600">TAIL</div>
              <div className="text-2xl font-bold text-yellow-600">
                {results.results.tail ? Object.keys(results.results.tail).length : 0}
              </div>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 px-6 pt-4 border-b overflow-x-auto">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-2 font-medium text-sm rounded-t-lg transition-colors flex items-center gap-2 whitespace-nowrap ${
                  activeTab === tab.id
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                <Icon size={16} />
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">{renderTabContent()}</div>

        {/* Errors */}
        {results.errors.length > 0 && (
          <div className="px-6 py-4 border-t bg-red-50">
            <div className="font-semibold text-red-800 mb-2">Errors:</div>
            <ul className="space-y-1">
              {results.errors.map((error, idx) => (
                <li key={idx} className="text-sm text-red-700">
                  {error}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Footer */}
        <div className="flex justify-end items-center p-6 border-t bg-gray-50">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
