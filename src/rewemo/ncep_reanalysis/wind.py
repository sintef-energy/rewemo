# -*- coding: utf-8 -*-
"""
Created on Mon Dec 11 10:06:30 2017

@author: hsven
"""

import pandas as pd
from matplotlib import pyplot as plt
#from mpl_toolkits.basemap import Basemap
#import mpl_toolkits.basemap
import netCDF4
from scipy.interpolate import interp1d
import datetime
import os
#import pyresample
import numpy as np
import timeseries_tools as tt


#datarange = {'lat': [40, 75], 'lon': [-10, 35],'year': [1948,2016]}
#powercurves = pd.read_csv('wind_powercurves_tradewind.csv',
#                          index_col=0)
#datapath='J:/DOK/12/hsven/reanalysis_data/nc_files'

class WindPower:

    def __init__(self,datarange):
        self.datarange = datarange
        self.nc_lats = None
        self.nc_lons = None
        self.lats_selected = None
        self.lons_r = None
        self.lons_selected = None
        self.coords = None
        self.powercurve_refs = None # if specified, list of which powercurve to use
        self.df_weight = None


    def getDataCoords(self):
        """Return latitudes and longitudes of Reanalysis data points"""
        return (self.nc_lats, self.nc_lons)

    def computepower(self,wind,powercurve):
        f = interp1d(powercurve.index, powercurve.values, kind='linear',
                     fill_value=(0,0),bounds_error=False)
        power = f(wind)
        return power


    def getAndValidateNcData(self,nc_path,year):

        datadict = {}
        nc_vwnd = netCDF4.Dataset('{}/vwnd.sig995.{}.nc'.format(nc_path,year))
        hv = nc_vwnd.variables['vwnd']
        nc_uwnd = netCDF4.Dataset('{}/uwnd.sig995.{}.nc'.format(nc_path,year))
        hu = nc_uwnd.variables['uwnd']
        nc_temp = netCDF4.Dataset('{}/air.sig995.{}.nc'.format(nc_path,year))
        hT = nc_temp.variables['air']
        nc_land_sea = netCDF4.Dataset('{}/land.nc'.format(nc_path))

        datadict['hv'] = hv
        datadict['hu'] = hu
        datadict['hT'] = hT
        datadict['nc_land_sea'] = nc_land_sea

        times = nc_vwnd.variables['time']
        if self.nc_lats is None:
            self.nc_lats = nc_vwnd.variables['lat']
            self.nc_lons = nc_vwnd.variables['lon']
        lats = self.nc_lats
        lons = self.nc_lons

        #Check that coordinates are the same:
        if not (nc_uwnd.variables['time'].actual_range
                == nc_vwnd.variables['time'].actual_range).all():
            raise Exception("Different times.")
        if not (nc_temp.variables['time'].actual_range
                == nc_vwnd.variables['time'].actual_range).all():
            raise Exception("Different times.")
        if list(nc_vwnd.variables['lat']) != list(lats):
            raise Exception("Different latitudes.")
        if list(nc_vwnd.variables['lon']) != list(lons):
            raise Exception("Different longitudes.")
        if list(nc_uwnd.variables['lat']) != list(lats):
            raise Exception("Different latitudes.")
        if list(nc_uwnd.variables['lon']) != list(lons):
            raise Exception("Different longitudes.")
        if list(nc_land_sea.variables['lon']) != list(lons):
            raise Exception("Different longitudes.")
        if list(nc_land_sea.variables['lat']) != list(lats):
            raise Exception("Different laitudes.")
        if list(nc_temp.variables['lat']) != list(lats):
            raise Exception("Different latitudes.")
        if list(nc_temp.variables['lon']) != list(lons):
            raise Exception("Different longitudes.")
        times = nc_vwnd.variables['time']

        jd = netCDF4.num2date(times[:],times.units,
            only_use_cftime_datetimes=False,only_use_python_datetimes=True)
        datadict['jd'] = jd

        # if data coordinates have not yet been specified (first run)
        if self.coords is None:
            # if no lat,lon points have been selected (use entire grid)
            if self.lats_selected is None:
                # Use all lat,lon pairs in the range
                self.lats_selected = [lat for lat in lats
                                 if ((lat>=self.datarange['lat'][0]) and
                                     (lat<=self.datarange['lat'][-1]))]
                self.lons_r = ([lon if lon<=180 else lon-360 for lon in lons])
                self.lons_selected = sorted([lon for lon in self.lons_r
                                 if ((lon>=self.datarange['lon'][0]) and
                                     (lon<=self.datarange['lon'][-1]))])
                self.coords = [(lat,lon) for lat in self.lats_selected
                               for lon in self.lons_selected]
            else:
                self.coords = pd.DataFrame({'lat':self.lats_selected,
                                        'lon':self.lons_selected})
            #= [(self.lats_selected[i],self.lons_selected[i])
            #                for i in range(len(self.lats_selected))]

        return datadict

    def makePowerTimeSeries(self,nc_path,outpath,powercurves,
                            windspeed_scaling=1.0,
                            remove_29feb=True,gzip=False):
        '''
        make wind power time series

        Parameters
        ==========
        nc_path : str
            Path where Reanalysis NC files are located
        outpath : str
            Path where generated time series should be placed
        powercurves : pandas dataframe
            Table giving powercurve
        windspeed_scaling : float or dict
            Scaling factor for wind speed, can be single number, or dictionary
            with different values for different (lat,lon) keys
        remove_29feb : bool
            Whether leap year days should be removed
        gzip : bool
            Whether to zip the output csv files
        '''
        wind = {}
        wind_onland = {}

        if not os.path.exists(outpath):
            print("Making path for output data:\n{}".format(outpath))
            os.makedirs(os.path.abspath(outpath))

        datarange = self.datarange

        for year in range(datarange['year'][0],datarange['year'][1]+1):
            datadict = self.getAndValidateNcData(nc_path,year)
            hu = datadict['hu']
            hv = datadict['hv']
            hT = datadict['hT']
            jd = datadict['jd']
            nc_land_sea = datadict['nc_land_sea']
            # Loop thorugh geo range of interest
            for k in self.coords:
                (lat,lon) = k
                ind_lat = list(self.nc_lats).index(lat)
                ind_lon = list(self.lons_r).index(lon)

                #hs = pd.Series(h[:,ind_lat,ind_lon],index=jd)
                thisone = pd.DataFrame({'vwnd':hv[:,ind_lat,ind_lon],
                                        'uwnd':hu[:,ind_lat,ind_lon],
                                        'T':hT[:,ind_lat,ind_lon]},index=jd)
                thisone['v'] = np.sqrt(np.square(thisone['uwnd'])
                                          +np.square(thisone['vwnd']))

                if k in wind:
                    wind[k] = pd.concat([wind[k],thisone],axis=0)
                else:
                    wind[k] = thisone

                if k not in wind_onland:
                    wind_onland[k] = nc_land_sea.variables['land'][
                                                0,ind_lat,ind_lon]

        print('{}: Done'.format(datetime.datetime.now()))

        print("Interploating to hourly wind speed values...")
        for k in wind:
            wind[k] = wind[k].resample('1H').interpolate('linear')
            # Add missing hours at the end 19,20,21,22,23:
            missinghours = 23-wind[k].index[-1].hour
            if missinghours!=5:
                raise Exception("Something is wrong")
            missingindx = pd.date_range(start=wind[k].index[-1]+1,
                                      periods=missinghours,freq='H')
            missingwind = wind[k].iloc[[-1]*missinghours].set_index(missingindx)
            wind[k] = wind[k].append(missingwind)

        # TODO: If necessary, 2d-interpolate to selected coordinates

        print("Computing power and exporting results...")
        summary = pd.DataFrame(self.coords,columns=['lat','lon'])
        self.powercurve_refs = pd.Series(index=wind.keys())
        for k in wind:
            print(k,end=" ")
            if wind_onland[k]:
                pc='avg_lowland_upland'
            else:
                pc='offshore'
            self.powercurve_refs.loc[k] = pc


            if isinstance(windspeed_scaling,dict):
                scaling = windspeed_scaling[k]
            else:
                scaling = windspeed_scaling
            wind[k]['power'] = self.computepower(
                    scaling*wind[k]['v'],powercurves[pc])
            timeseries_data=wind[k]
            if remove_29feb:
                mask = ((wind[k].index.month==2) & (wind[k].index.day==29))
                timeseries_data = wind[k][~mask]

            if gzip:
                timeseries_data.to_csv(
                        '{}/wind_{}_pc{}.csv.gz'.format(outpath,k,pc),
                        compression="gzip")
            else:
                timeseries_data.to_csv(
                        '{}/wind_{}_pc{}.csv'.format(outpath,k,pc))

            for c in timeseries_data.keys():
                summary.loc[self.coords.index(k),c] = timeseries_data[c].mean()
        summary.to_csv('{}/wind_SUMMARY.csv'.format(outpath))

        return (wind,wind_onland)



    def computeInterpolationWeights(self,Ninterpolate=3):
        '''Compute geographical interpolation weights

        parameters
        ----------
        Ninterpolate : int
          number of points to interpolate (N=1: nearest neighbour)

        returns
        -------
        df_weight : pandas.DataFrame
          NxM table of interpolation weights. The columns are the M selected
          points of interest, and rows are tne N grid points.
        '''
        print("Determining geographical interpolation weights")
        latlon_grid = tt.getDataGrid(self.nc_lats,self.nc_lons)
        latlon_select = pd.DataFrame({
            'lats':self.lats_selected,
            'lon':self.lons_selected})
        df_weight = tt.computeInterpolationWeights(
                latlon_grid,latlon_select,Ninterpolate)
        return df_weight

    def makePowerTimeSeriesSelection(self,nc_path,powercurves,
        windspeed_scaling=1.0, Ninterpolate=3):
        '''
        make wind power time series for selected lat,lons, using interpolation

        Parameters
        ==========
        nc_path : str
            Path where Reanalysis NC files are located
        powercurves : pandas dataframe
            Table giving powercurve
        windspeed_scaling : float or dict
            Scaling factor for wind speed, can be single number, or dictionary
            with different values for different (lat,lon) keys
        Ninterpolate : int
            number of nearest neighbours used for interpolation
        '''
        wind = {}

        years = self.datarange['year']

        for year in range(years[0],years[1]+1):
            print('{}: Year={}'.format(datetime.datetime.now(),year))
            datadict = self.getAndValidateNcData(nc_path,year)

            hu = datadict['hu']
            hv = datadict['hv']
            hT = datadict['hT']
            jd = datadict['jd']
            vdim = hu.shape[0]
            # 1464x73x144 (time x lat x lon) -> 1464x10512 (time x latlon_grid)
            hv_2d = hv[:].reshape((vdim,-1),order="C")
            hu_2d = hu[:].reshape((vdim,-1),order="C")
            hT_2d = hT[:].reshape((vdim,-1),order="C")

            # If not done before, calculate geographical interpolation weights:
            if self.df_weight is None:
                self.df_weight = self.computeInterpolationWeights()
            for i in self.df_weight.columns:
                thisone = pd.DataFrame(
                        {'vwnd':hv_2d.dot(self.df_weight[i]),
                         'uwnd':hu_2d.dot(self.df_weight[i]),
                         'T':hT_2d.dot(self.df_weight[i])},
                         index=pd.to_datetime(jd))
                thisone['v_calc'] = np.sqrt(np.square(thisone['uwnd'])
                                          +np.square(thisone['vwnd']))
                thisone['v'] = np.sqrt(np.square(hu_2d)
                                          +np.square(hv_2d)).dot(self.df_weight[i])
                #print("thisone = ",thisone.index)
                if i in wind:
                    wind[i] = pd.concat([wind[i],thisone],axis=0)
                else:
                    wind[i] = thisone

        print('{}: Done'.format(datetime.datetime.now()))

        print("Interploating to hourly wind speed values...")
        for k in wind:
            wind[k] = wind[k].resample('1H').interpolate('linear')
            # Add missing hours at the end 19,20,21,22,23:
            missinghours = 23-wind[k].index[-1].hour
            if missinghours!=5:
                raise Exception("Something is wrong")
            missingindx = pd.date_range(start=wind[k].index[-1]
                                        +datetime.timedelta(hours=1),
                                      periods=missinghours,freq='H')
            missingwind = wind[k].iloc[[-1]*missinghours].set_index(missingindx)
            wind[k] = wind[k].append(missingwind)

        print("Computing power from wind speed...")
        for k in wind:
            print(k,end=" ")
            pc = self.powercurve_refs[k]

            if isinstance(windspeed_scaling,dict):
                scaling = windspeed_scaling[k]
            else:
                scaling = windspeed_scaling
            wind[k]['power'] = self.computepower(
                    scaling*wind[k]['v'],powercurves[pc])

        return wind




    def plotTimeseries(self,outpath,windpower,wind_onland=None,k_plot=None):

        df_coords = pd.DataFrame(self.coords,columns=['lat','lon'])
        if wind_onland is not None:
            df_coords['onland'] = [wind_onland[k] for k in self.coords]
        if k_plot is None:
            k_plot = list(windpower.keys())[0]

        fig = plt.figure(figsize=(6,3))
        #ax = fig.add_subplot(111)
        ax1 = windpower[k_plot]['v'].plot(label="Speed",title='{} at {}'.format('wind',k_plot))
        ax2 = windpower[k_plot]['power'].plot(label="Power",ax=ax1,secondary_y=True)
        ax1.set_ylabel('m/s')
        ax2.set_ylabel('p.u.')
        plt.xlabel("Time")
        lines = ax1.get_lines() + ax2.get_lines()
        ax1.legend(lines, [line.get_label() for line in lines])
        #plt.ylabel("MW")
        #plt.gcf().set_size_inches(6,3)
        plt.savefig(os.path.join(outpath,"fig_wind_speedpower.png"),
                    bbox_inches = 'tight')

        fig = plt.figure(figsize=(12,4))
        ax = fig.add_subplot(111)
        windpower[k_plot]['T'].plot(ax=ax,title='{} at {}'.format('Temperature (sig995)',k_plot))
        plt.ylabel("K")
        plt.gcf().set_size_inches(6,3)
        plt.xlabel("Time")
        plt.savefig(os.path.join(outpath,"fig_temperature_sig995.png"),
                    bbox_inches = 'tight')

    def plotPoints(self,outpath,wind_onland=None,labels=True):
        df_coords = pd.DataFrame(self.coords,columns=['lat','lon'])
        if wind_onland is not None:
            df_coords['onland'] = [wind_onland[k] for k in self.coords]
        plt.figure()
        # projections: cyl, mill
        m = mpl_toolkits.basemap.Basemap(projection='mill',resolution='l',
                    llcrnrlon=-11,llcrnrlat=39,urcrnrlon=36,urcrnrlat=76,
                    lat_0=60,lon_0=10)
        m.drawcoastlines(linewidth=0.25)
        m.drawcountries(linewidth=0.25)
        #m.fillcontinents(color='coral',lake_color='aqua')
        m.drawmeridians(np.arange(0,360,10),labels=[True,True,True,True])
        m.drawparallels(np.arange(-90,90,10),labels=[True,True,True,True])
        x,y = m(df_coords['lon'].values,df_coords['lat'].values)
#        if wind_onland is None:
#            colours = 'r'
#        else:
#            colours = ['r' if k==1 else 'b' for k in df_coords['onland']]
        labs, levs = self.powercurve_refs.factorize()
        m.scatter(x,y,marker='o',c=labs,cmap=plt.cm.Set1,vmin=0,vmax=8)
        if labels:
            for i in df_coords.index:
                plt.text(x[i], y[i],i)
        plt.gcf().set_size_inches(6,6)
        plt.savefig(os.path.join(outpath,"fig_datapoints_sig995.png"),
                    bbox_inches = 'tight')


    def plotContour(self,outpath,windpower):
        df_coords = pd.DataFrame(self.coords,columns=['lat','lon'])
        plt.figure()
        # projections: cyl, mill
        m = mpl_toolkits.basemap.Basemap(projection='mill',resolution='l',
                    llcrnrlon=-11,llcrnrlat=39,urcrnrlon=36,urcrnrlat=76,
                    lat_0=60,lon_0=10)
        m.drawcoastlines(linewidth=0.25)
        m.drawcountries(linewidth=0.25)
        #labels = [left,right,top,bottom]
        m.drawmeridians(np.arange(0,360,10),labels=[True,False,True,True])
        m.drawparallels(np.arange(-90,90,10),labels=[True,False,True,True])
        x,y = m(df_coords['lon'].values,df_coords['lat'].values)
        nx=len(self.lons_selected)
        ny=len(self.lats_selected)
        data=[w['power'].mean() for i,w in windpower.items()]
        data2=np.array(data).reshape(ny,nx)
        cs = m.contourf(x.reshape(ny,nx),y.reshape(ny,nx),data2,cmap=plt.cm.viridis)
        m.scatter(x,y,marker='o',edgecolor='k',c=data,cmap=plt.cm.jet)
        cbar = m.colorbar(cs)
        cbar.set_label('Mean capacity factor')
        plt.gcf().set_size_inches(6,6)
        plt.savefig(os.path.join(outpath,"fig_wind_capacityfactor_mean.png"),
                    bbox_inches = 'tight')
