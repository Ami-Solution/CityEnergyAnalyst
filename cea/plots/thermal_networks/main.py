"""
This file runs all plots of the CEA
"""

from __future__ import division
from __future__ import print_function

import time
import os

import pandas as pd
import numpy as np
import networkx as nx

import cea.config
import cea.inputlocator
from cea.plots.thermal_networks.loss_curve import loss_curve
from cea.plots.thermal_networks.distance_loss_curve import distance_loss_curve
from cea.plots.thermal_networks.Supply_Return_Outdoor import supply_return_ambient_temp_plot
from cea.plots.thermal_networks.loss_duration_curve import loss_duration_curve
from cea.plots.thermal_networks.network_plot import network_plot

__author__ = "Jimeno A. Fonseca"
__copyright__ = "Copyright 2018, Architecture and Building Systems - ETH Zurich"
__credits__ = ["Jimeno A. Fonseca"]
__license__ = "MIT"
__version__ = "0.1"
__maintainer__ = "Daren Thomas"
__email__ = "cea@arch.ethz.ch"
__status__ = "Production"


def plots_main(locator, config):
    # initialize timer
    t0 = time.clock()

    # local variables
    network_type = config.plots.network_type
    network_names = config.plots.network_names

    # initialize class
    plots = Plots(locator, network_type, network_names)

    plots.loss_curve()
    plots.loss_curve_relative()
#    plots.distance_Tloss_curve()
#    plots.distance_ploss_curve()
    plots.supply_return_ambient_curve()
    plots.loss_duration_curve()
    plots.heat_network_plot()
    plots.pressure_network_plot()

    # print execution time
    time_elapsed = time.clock() - t0
    print('done - time elapsed: %d.2f seconds' % time_elapsed)

    return


class Plots():

    def __init__(self, locator, network_type, network_name):
        self.locator = locator
        self.demand_analysis_fields = ["Qhsf_kWh",
                                       "Qwwf_kWh",
                                       "Qcsf_kWh"]
        self.network_name = self.preprocess_network_name(network_name)
        self.network_type = network_type
        self.plot_title_tail = self.preprocess_plot_title()
        self.plot_output_path_header = self.preprocess_plot_outputpath()
        self.readin_path = self.locator.get_network_layout_edges_shapefile(network_type, self.network_name)

        self.q_data_processed = self.preprocessing_heat_loss()
        self.p_data_processed = self.preprocessing_pressure_loss()
        self.q_network_data_rel_processed = self.preprocessing_rel_loss(self.q_data_processed['hourly_network_loss'])
        self.p_data_rel_processed = self.preprocessing_rel_loss(self.p_data_processed['hourly_loss'])
        self.p_distance_data_processed = self.preprocessing_node_pressure()
        self.T_distance_data_processed = self.preprocessing_node_temperature()
        self.network_processed = self.preprocessing_network_graph()
        self.ambient_temp = self.preprocessing_ambient_temp()
        self.plant_temp_data_processed = self.preprocessing_plant_temp()
        self.network_data_processed = self.preprocessing_network_data()
        self.demand_data = self.preprocessing_building_demand()

    def preprocess_network_name(self, network_name):
        '''
        Readin network name and format as a string
        '''
        if network_name == []:
            return ""
        else:
            return str(network_name)

    def preprocess_plot_outputpath(self):
        '''
        Define output path for the plots
        '''
        if self.network_type == []:  # get network type, default is DH__
            return "DH_" + str(self.network_name) + "_"
        elif len(self.network_type) >= 1:
            return str(self.network_type) + "_" + str(self.network_name) + "_"
        else:  # should never happen / should not be possible
            return "DH_" + str(self.network_name) + "_"

    def preprocess_plot_title(self):
        '''
        Format plot title ending to include network type and network name
        '''
        if not self.network_name:
            if self.network_type == []:  # get network type, default is DH
                return " for DH"
            elif len(self.network_type) == 2:
                return " for " + str(self.network_type)
            else:  # should never happen / should not be possible
                return ""
        else:
            if self.network_type == []:  # get network type, default is DH
                return " for DH in " + str(self.network_name)
            elif len(self.network_type) == 2:
                return " for " + str(self.network_type) + " in " + str(self.network_name)
            else:  # should never happen / should not be possible
                return " in " + str(self.network_name)


    def preprocessing_building_demand(self):
        buildings = self.locator.get_zone_building_names()
        for i, building in enumerate(buildings):
            if i == 0:
                df = pd.read_csv(self.locator.get_demand_results_file(building))
                if self.network_type == 'DH':
                    df5 = pd.DataFrame(df["Qhsf_kWh"]+df["Qwwf_kWh"])
                    df5.columns = [str(building)]
                else:
                    df5 = pd.DataFrame(df['Qcsf_kWh'])
                    df5.columns = [str(building)]
            else:
                df2 = pd.read_csv(self.locator.get_demand_results_file(building))
                for field in self.demand_analysis_fields:
                    df[field] = df[field].values + df2[field].values
                if self.network_type == 'DH':
                    df6 = pd.DataFrame(df2["Qhsf_kWh"]+df2["Qwwf_kWh"])
                    df6.columns = [str(building)]
                else:
                    df6 = pd.DataFrame(df2['Qcsf_kWh'])
                    df6.columns = [str(building)]
                df5 = df5.join(df6)

        df3 = pd.read_csv(self.locator.get_total_demand())

        if self.network_type == 'DH':
            df4 = pd.DataFrame(df["Qhsf_kWh"]).join(pd.DataFrame(df["Qwwf_kWh"]))
        else:
            df4 = pd.DataFrame(df['Qcsf_kWh'])

        return {"hourly_loads": df4.set_index(df['DATE']), "yearly_loads": df3, "buildings_hourly": df5}


    def preprocessing_ambient_temp(self):
        '''
        Read in ambient temperature data at first building
        This assumes that all buildings are relatively close to each other
        '''
        building_names = self.locator.get_zone_building_names()
        building_name = building_names[0]
        demand_file = pd.read_csv(self.locator.get_demand_results_file(building_name))
        ambient_temp = demand_file["T_ext_C"].values
        return pd.DataFrame(ambient_temp)

    def preprocessing_plant_temp(self):
        '''
        Read in and format plant supply and return temperatures
        '''
        plant_nodes = self.preprocessing_network_graph()["Plants_names"]
        df_s = pd.read_csv(self.locator.get_Tnode_s(self.network_name, self.network_type))
        df_r = pd.read_csv(self.locator.get_Tnode_r(self.network_name, self.network_type))
        df = pd.DataFrame()
        for i in range(len(plant_nodes)):
            df['Supply_'+str(plant_nodes[i])] = pd.DataFrame(df_s[str(plant_nodes[i])])-273.15
            df['Return_'+str(plant_nodes[i])] = pd.DataFrame(df_r[str(plant_nodes[i])])-273.15
        return {'Data': df, 'Plants': plant_nodes}

    def preprocessing_heat_loss(self):
        '''
        Read in and format edge heat losses for all 8760 time steps
        '''
        df = pd.read_csv(self.locator.get_qloss(self.network_name, self.network_type))
        df = abs(df).sum(axis=1)
        df1 = abs(df.values).sum() #sum over all timesteps
        return {"hourly_network_loss": pd.DataFrame(df), "yearly_loss": df1}

    def preprocessing_pressure_loss(self):
        '''
        Read in pressure loss data for all time steps.
        '''
        df = pd.read_csv(self.locator.get_ploss(self.network_name, self.network_type))
        df = df['pressure_loss_total_kW']
        df1 = df.values.sum()
        return {"hourly_loss": pd.DataFrame(df), "yearly_loss": df1}

    def preprocessing_rel_loss(self, absolute_loss):
        '''
        Calculate relative heat or pressure loss:
        1. Sum up all plant heat produced in each time step
        2. Divide absolute losses by that value
        '''
        df = pd.read_csv(self.locator.get_qplant(self.network_name, self.network_type))  # read plant heat supply
        df = abs(df)
        if len(df.columns.values) > 1:  # sum of all plants
            df = df.sum(axis=1)
        df[df == 0] = np.nan
        df = np.reshape(df.values, (8760,1))
        rel = absolute_loss.values / df * 100
        rel[rel == 0] = np.nan
        mean_loss = np.nanmean(rel)
        rel = np.round(rel, 2)
        mean_loss = np.round(mean_loss, 2)
        return {"hourly_loss": pd.DataFrame(rel), "average_loss": mean_loss}

    def preprocessing_node_pressure(self):
        '''
        Read in and format node supply and return pressure in each node.
        Find minimum, maximum and average values.
        '''
        df_s = pd.read_csv(self.locator.get_pnode_s(self.network_name, self.network_type))
        df_r = pd.read_csv(self.locator.get_pnode_r(self.network_name, self.network_type))
        df_s[df_s == 0] = np.nan
        df_r[df_r == 0] = np.nan
        df1 = df_s.min()
        df2 = df_s.mean()
        # df2 = df_s.ix[1424]
        df3 = df_s.max()
        df4 = df_r.min()
        df5 = df_r.mean()
        # df5 = df_r.ix[1424]
        df6 = df_r.max()
        return pd.concat([df1, df4, df3, df6, df2, df5], axis=1)

    def preprocessing_node_temperature(self):
        '''
        Read in and format node supply and return Temperature in each node.
        Find minimum, maximum and average values.
        '''
        df_s = pd.read_csv(self.locator.get_Tnode_s(self.network_name, self.network_type))-273.15
        df_r = pd.read_csv(self.locator.get_Tnode_r(self.network_name, self.network_type))-273.15
        df_s[df_s == 0] = np.nan
        df_r[df_r == 0] = np.nan
        df1 = df_s.min()
        df2 = df_s.mean()
        df3 = df_s.max()
        df4 = df_r.min()
        df5 = df_r.mean()
        df6 = df_r.max()
        return pd.concat([df1, df4, df3, df6, df2, df5], axis=1)

    def preprocessing_network_graph(self):
        '''
        Setup network graph, find shortest path between each plant and each node.
        Identify node coordinates.
        '''
        # read in edge node matrix
        df = pd.read_csv(self.locator.get_optimization_network_edge_node_matrix_file(self.network_type,
                                                                                     self.network_name),
                         index_col=0)
        # read in edge lengths
        edge_data = pd.read_csv(self.locator.get_optimization_network_edge_list_file(self.network_type,
                                                                                     self.network_name),
                                index_col=0)
        edge_lengths = edge_data['pipe length']

        # identify number of plants and nodes
        plant_nodes = []
        plant_nodes_names = []
        for node, node_index in zip(df.index, range(len(df.index))):
            if max(df.ix[node]) <= 0:  # only -1 and 0 so plant!
                plant_nodes.append(node_index)
                plant_nodes_names.append(node)
        # convert df to networkx type graph
        df = np.transpose(df)  # transpose matrix to more intuitively setup graph
        graph = nx.Graph()  # set up networkx type graph
        for i in range(df.shape[0]):
            new_edge = [0, 0]
            for j in range(0, df.shape[1]):
                if df.iloc[i][df.columns[j]] == 1:
                    new_edge[0] = j
                elif df.iloc[i][df.columns[j]] == -1:
                    new_edge[1] = j
            graph.add_edge(new_edge[0], new_edge[1], edge_number=i, weight=edge_lengths[i])  # add edges to graph

        # make a list of shortest distances from plant, one row per plant, for all nodes
        plant_distance = np.zeros((len(plant_nodes), len(graph.nodes())))
        for plant_node, plant_index in zip(plant_nodes, range(len(plant_nodes))):
            for node in graph.nodes():
                plant_distance[plant_index, node] = nx.shortest_path_length(graph, plant_node, node, weight='weight')
        plant_distance = np.round(plant_distance, 0)

        # find node coordinates
        # read in 3 columns of alledges
        coords = edge_data['geometry']
        start_nodes = edge_data['start node']
        end_nodes = edge_data['end node']
        coordinates = {}
        for edge, edge_number in zip(coords, range(len(coords))):
            edge = edge.replace("(", "")
            edge = edge.replace(")", "")
            edge = edge.replace(",", "")
            edge = edge.split(" ")
            if not start_nodes[edge_number] in coordinates.keys():
                coordinates[start_nodes[edge_number]] = float(edge[1]), float(edge[2])
            if not end_nodes[edge_number] in coordinates.keys():
                coordinates[end_nodes[edge_number]] = float(edge[3]), float(edge[4])

        return {"Distances": pd.DataFrame(plant_distance), "Network": graph, "Plants": plant_nodes,
                "Plants_names": plant_nodes_names,
                'edge_node': np.transpose(df), 'coordinates': coordinates}

    def preprocessing_network_data(self):
        '''
        Read in and format network data such as diameters, hourly node temperatures and pressures,
        edge heat and pressure losses
        '''
        # read in edge diameters
        edge_data = pd.read_csv(self.locator.get_optimization_network_edge_list_file(self.network_type,
                                                                                     self.network_name),
                                index_col=0)
        edge_diam = edge_data['D_int_m']
        d1 = pd.read_csv(self.locator.get_Tnode_s(self.network_name, self.network_type))-273.15
        d2 = pd.read_csv(self.locator.get_optimization_network_layout_qloss_file(self.network_type,
                                                                                 self.network_name))
        d3 = np.round(pd.read_csv(self.locator.get_pnode_s(self.network_name, self.network_type)) / 1000, 0)
        d4 = pd.read_csv(self.locator.get_optimization_network_layout_ploss_file(self.network_type,
                                                                                 self.network_name))
        diam = pd.DataFrame(edge_diam)
        return {'Diameters': diam, 'Tnode_hourly_C': d1, 'Qedge-loss_hourly_kW': d2, 'Pnode_hourly_kPa': d3,
                'Pedge-loss_hourly_kW': d4}

    def preprocessing_costs_scenarios(self):
        data_processed = pd.DataFrame()
        for scenario in self.scenarios:
            locator = cea.inputlocator.InputLocator(scenario)
            scenario_name = os.path.basename(scenario)
            data_raw = 0 #todo: once cost data available, read in here
            data_raw_df = pd.DataFrame({scenario_name: data_raw}, index=data_raw.index).T
            data_processed = data_processed.append(data_raw_df)
        return data_processed

    #todo: move this and the following into one function
    def loss_curve(self):
        title = "Heat and Pressure Losses" + self.plot_title_tail
        output_path = self.locator.get_timeseries_plots_file(self.plot_output_path_header + '_losses_curve')
        analysis_fields = ["Epump_loss_kWh", "Qnetwork_loss_kWh"]
        for column in self.demand_data['hourly_loads'].columns:
            analysis_fields = analysis_fields + [str(column)]
        data = self.p_data_processed['hourly_loss'].join(self.q_data_processed['hourly_network_loss'])
        data.index = self.demand_data['hourly_loads'].index
        data = data.join(self.demand_data['hourly_loads'])
        data.columns = analysis_fields
        plot = loss_curve(data, analysis_fields, title, output_path)
        return plot

    def loss_curve_relative(self):
        title = "Relative Heat and Pressure Losses" + self.plot_title_tail
        output_path = self.locator.get_timeseries_plots_file(self.plot_output_path_header + '_relative_losses_curve')
        analysis_fields = ["Epump_loss_%", "Qnetwork_loss_%"]
        for column in self.demand_data['hourly_loads'].columns:
            analysis_fields = analysis_fields + [str(column)]
        df = self.p_data_rel_processed['hourly_loss']
        df = df.rename(columns={0: 1})
        data = df.join(self.q_network_data_rel_processed['hourly_loss'])
        data.index = self.demand_data['hourly_loads'].index
        data = data.join(self.demand_data['hourly_loads'])
        data.columns = analysis_fields
        plot = loss_curve(data, analysis_fields, title, output_path)
        return plot

    def distance_ploss_curve(self):
        title = "Pressure losses relative to plant distance " + self.plot_title_tail
        output_path = self.locator.get_timeseries_plots_file(self.plot_output_path_header + '_distance_plosses_curve')
        analysis_fields = ["P-sup_node_min_Pa",
                           "P-ret_node_min_Pa",
                           "P-sup_node_max_Pa",
                           "P-ret_node_max_Pa",
                           "P-sup_node_mean_Pa",
                           "P-ret_node_mean_Pa"]
        data = self.p_distance_data_processed
        data2 = self.network_processed["Distances"]
        data.columns = analysis_fields
        plants = self.network_processed["Plants"]
        plot = distance_loss_curve(data, data2, analysis_fields, title, output_path, 'Pressure [Pa]', plants)
        return plot

    def distance_Tloss_curve(self):
        title = "Temperature losses relative to plant distance " + self.plot_title_tail
        output_path = self.locator.get_timeseries_plots_file(self.plot_output_path_header + '_distance_Tlosses_curve')
        analysis_fields = ["T-sup_node_min_K",
                           "T-ret_node_min_K",
                           "T-sup_node_max_K",
                           "T-ret_node_max_K",
                           "T-sup_node_mean_K",
                           "T-ret_node_mean_K"]
        data = self.T_distance_data_processed
        data2 = self.network_processed["Distances"]
        plants = self.network_processed["Plants"]
        data.columns = analysis_fields
        plot = distance_loss_curve(data, data2, analysis_fields, title, output_path, 'Temperature [K]', plants)
        return plot

    def supply_return_ambient_curve(self):
        title = "Supply and Return Temperature relative to Ambient Temperature" + self.plot_title_tail
        analysis_fields = ["T-sup_plant_K", "T-ret_plant_K"]
        data = self.plant_temp_data_processed['Data']
        data2 = self.ambient_temp
        plant_nodes = self.plant_temp_data_processed['Plants']
        for i in range(len(plant_nodes)):
            data_part = pd.DataFrame()
            data_part['0'] = data['Supply_' + str(plant_nodes[i])]
            data_part['1'] = data['Return_' + str(plant_nodes[i])]
            output_path = self.locator.get_timeseries_plots_file(self.plot_output_path_header +
                                                                 '_Tamb_Tsup_Tret_curve_plantnode' + str(i))
            data_part.columns = analysis_fields
            plot = supply_return_ambient_temp_plot(data_part, data2, analysis_fields, title, output_path)
        return plot

    def loss_duration_curve(self):
        title = "Loss Duration Curve" + self.plot_title_tail
        output_path = self.locator.get_timeseries_plots_file(self.plot_output_path_header + '_loss_duration_curve')
        analysis_fields = ["Epump_loss_kWh", "Qnetwork_loss_kWh"]
        data = self.p_data_processed['hourly_loss'].join(self.q_data_processed['hourly_network_loss'])
        data.columns = analysis_fields
        plot = loss_duration_curve(data, analysis_fields, title, output_path)
        return plot

    def heat_network_plot(self):
        title = "Thermal network " + self.plot_title_tail
        output_path = self.locator.get_networks_plots_file(self.plot_output_path_header + '_thermal_network')
        analysis_fields = ['Tnode_hourly_C', 'Qedge-loss_hourly_kW']
        all_nodes = pd.read_csv(self.locator.get_optimization_network_node_list_file(self.network_type, self.network_name))
        data = {'Diameters': self.network_data_processed['Diameters'],
                'coordinates': self.network_processed['coordinates'],
                'edge_node': self.network_processed['edge_node'],
                analysis_fields[0]: self.network_data_processed[analysis_fields[0]],
                analysis_fields[1]: self.network_data_processed[analysis_fields[1]]}
        building_demand_data = self.demand_data['buildings_hourly']
        plot = network_plot(data, title, output_path, analysis_fields, building_demand_data, all_nodes)
        return plot

    def pressure_network_plot(self):
        title = "Hydraulic network " + self.plot_title_tail
        output_path = self.locator.get_networks_plots_file(self.plot_output_path_header + '_hydraulic_network')
        analysis_fields = ['Pnode_hourly_kPa', 'Pedge-loss_hourly_kW']
        all_nodes = pd.read_csv(self.locator.get_optimization_network_node_list_file(self.network_type, self.network_name))
        data = {'Diameters': self.network_data_processed['Diameters'],
                'coordinates': self.network_processed['coordinates'],
                'edge_node': self.network_processed['edge_node'],
                analysis_fields[0]: self.network_data_processed[analysis_fields[0]],
                analysis_fields[1]: self.network_data_processed[analysis_fields[1]]}
        building_demand_data = self.demand_data['buildings_hourly']
        plot = network_plot(data, title, output_path, analysis_fields, building_demand_data, all_nodes)
        return plot


def main(config):
    locator = cea.inputlocator.InputLocator(config.scenario)
    plots_main(locator, config)


if __name__ == '__main__':
    main(cea.config.Configuration())