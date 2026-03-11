import pandas as pd
from requests import Response
from io import BytesIO

from OMIEData.FileReaders.omie_file_reader import OMIEFileReader
from OMIEData.Enums.all_enums import TechnologyType


class EnergyByTechnologyHourlyFileReader(OMIEFileReader):

    # List of periods of data per hour. If file format changes, the day of change should be listed at
    # the TOP of the list in order to iterate backwards in time to be able to find the correct number.
    __periods_per_hour__ = (
        (dt.date(2025,  9, 25),  4),    # Updated in October 2025 to quarterly data
        (dt.date(1998,  1,  1),  1)     # Data is published since January 1, 1998 in hourly intervals
    )
    
    def __init__(self, frequency: string, types=None):

        self.conceptsToLoad = [v for v in TechnologyType] if not types else types

        match(frequency):
            case "hour": 
                self.__hourly_periods_output__ = 1
            case "quarter_hour": 
                self.__hourly_periods_output__ = 4
            case "minute":
                self.__hourly_periods_output__ = 60
            case _:
                raise ValueError("Unsupported number of datapoints per hour")
        
        self._dict_column_concept = {'Fecha': 'DATE',
                                     'Hora': 'HOUR',
                                     'CARBÓN': 'COAL',
                                     'FUEL-GAS': 'FUEL_GAS',
                                     'AUTOPRODUCTOR': 'SELF_PRODUCER',
                                     'NUCLEAR': 'NUCLEAR',
                                     'HIDRÁULICA': 'HYDRO',
                                     'CICLO COMBINADO': 'COMBINED_CYCLE',
                                     'EÓLICA': 'WIND',
                                     'SOLAR TÉRMICA': 'THERMAL_SOLAR',
                                     'SOLAR FOTOVOLTAICA': 'PHOTOVOLTAIC_SOLAR',
                                     'COGENERACIÓN/RESIDUOS/MINI HIDRA': 'RESIDUALS',
                                     'IMPORTACIÓN INTER.': 'IMPORT',
                                     'IMPORTACIÓN INTER. SIN MIBEL': 'IMPORT_WITHOUT_MIBEL'}

    def get_keys(self) -> list:

        key_list_retrieve = ['DATE', 'HOUR']
        key_list_retrieve.extend([str(v) for v in self.conceptsToLoad])
        return key_list_retrieve

    def get_hourly_periods_input(self, date: datetime) -> int:
        i = 0
        while self.__periods_per_hour__[i][0] > date:
            i += 1
        return self.__periods_per_hour__[i][1]

    def get_list_rows(self, num_hours: int) -> pd.Series:
        list_rows = []
        for hour in range(1, num_hours+1):
            for subperiod in range(1, self.__hourly_periods_output__+1):
                list_rows.append("H" + str(hour).zfill(2) + "_" + str(subperiod).zfill(2))

    def get_data_from_response(self, response: Response) -> pd.DataFrame:
        return self._get_data_from_file_like(file_like=BytesIO(response.content))

    def get_data_from_file(self, filename: str) -> pd.DataFrame:
        return self._get_data_from_file_like(file_like=filename)

    def _get_data_from_file_like(self, file_like) -> pd.DataFrame:
        df = pd.read_csv(file_like, sep=';', skiprows=2, header=0, encoding='latin-1', skipfooter=1, engine='python',
                         decimal=",", thousands='.')
        df = df.rename({k: v for k, v in self._dict_column_concept.items()}, axis=1)
        df = df[[x for x in self.get_keys()]]

        df["DATE"] = pd.to_datetime(df["DATE"], dayfirst=True, errors="coerce").dt.date
        # df["DATE"] = df["DATE"].dt.to_pydatetime()

        date = df.iloc[0]["DATE"]
        num_hours = df.shape[0] // self.get_hourly_periods_input(date)
        new_length = num_hours * self.__hourly_periods_output__
        df_processed = self._process_df_rows(old_df = df.drop(['DATE', 'PERIOD'], axis=1), new_length = new_length)
        df_processed["DATE"] = pd.Series([date] * new_length)
        df_processed["PERIOD"] = self.get_list_rows(num_hours = num_hours)
        return df_processed

    def _process_df_rows(self, old_df: pd.DataFrame, new_length: int) -> pd.DataFrame:
        old_length = old_df.shape[0]
        intermediate_df = old_df.copy()
        
        if old_length == new_length:
            new_df = intermediate_df
        
        elif old_length < new_length:
            new_df = pd.DataFrame(columns=intermediate_df.columns)
            for i in range(0, new_length):
                new_df.loc[i] = intermediate_df.iloc[(i * old_length) // new_length]
        
        elif old_length > new_length:
            rows_per_group = intermediate_df.shape[0] // new_length
            intermediate_df['GROUPING'] = intermediate_df.index // rows_per_group
            new_df = intermediate_df.groupby('GROUPING').mean()

        return new_df
