import datetime as dt
from babel.numbers import parse_decimal
import re
import numpy as np
import pandas as pd
from OMIEData.Enums.all_enums import DataTypeInMarginalPriceFile
from OMIEData.FileReaders.omie_file_reader import OMIEFileReader
from requests import Response


class AdjustmentPriceFileReader(OMIEFileReader):
    __dic_static_concepts__ = {
        "Precio de ajuste en el sistema portugués (EUR/MWh)": [
            DataTypeInMarginalPriceFile.PRICE_PORTUGAL,
            1.0,
        ]
    }

    __dateFormatInFile__ = "%d/%m/%Y"
    __localeInFile__ = "en_DK.UTF-8"

    # List of periods of data per hour. If file format changes, the day of change should be listed at
    # the TOP of the list in order to iterate backwards in time to be able to find the correct number.
    __periods_per_hour__ = (
        (dt.date(2025, 10,  1),  4),    # Updated in October 2025 to quarterly data
        (dt.date(1998,  1,  1),  1)     # Data is published since January 1, 1998 in hourly intervals
    )

    def __init__(self, types=None):
        self.conceptsToLoad = [v for v in DataTypeInMarginalPriceFile] if not types else types

        match(frequency):
            case "hour": 
                self.__hourly_periods_output__ = 1
            case "quarter_hour": 
                self.__hourly_periods_output__ = 4
            case "minute":
                self.__hourly_periods_output__ = 60
            case _:
                raise ValueError("Unsupported number of datapoints per hour")
        
        self.__key_list_retrieve__ = ['DATE', 'CONCEPT']
        for i in range(1, 26):
            for j in range (1, self.__hourly_periods_output__ + 1):
                self.__key_list_retrieve__.append('H' + str(i).zfill(2) + '_' + str(j).zfill(2))

    def get_keys(self):
        return self.__key_list_retrieve__

    def get_hourly_periods_input(self, date: datetime) -> int:
        i = 0
        while self.__periods_per_hour__[i][0] > date:
            i += 1
        return self.__periods_per_hour__[i][1]

    def get_data_from_response(self, response: Response) -> pd.DataFrame:
        res = pd.DataFrame(columns=self.get_keys())

        # from first line we get the units and the price date. We just look at the date
        lines = response.text.split("\n")
        matches = re.findall("\d\d/\d\d/\d\d\d\d", lines.pop(0))  # noqa: W605
        if not (len(matches) == 2):
            print('Response ' + response.url + ' does not have the expected format.')
        else:
            # The second date is the one we want
            date = dt.datetime.strptime(matches[1], AdjustmentPriceFileReader.__dateFormatInFile__).date()
            periods_per_hour_input = self.get_hourly_periods_input(date)
            # Process all the lines

            while lines:
                # read following line
                line = lines.pop(0)
                splits = line.split(sep=";")
                first_col = splits[0]

                if (
                    first_col
                    in AdjustmentPriceFileReader.__dic_static_concepts__.keys()
                ):
                    concept_type = AdjustmentPriceFileReader.__dic_static_concepts__[
                        first_col
                    ][0]

                    if concept_type in self.conceptsToLoad:
                        units = AdjustmentPriceFileReader.__dic_static_concepts__[
                            first_col
                        ][1]

                        dico = self._process_line(date=date, 
                                                  concept=concept_type, 
                                                  values=splits[1:], 
                                                  multiplier=units,
                                                  periods_per_hour_input=periods_per_hour_input)
                        res = pd.concat([res, pd.DataFrame([dico])], ignore_index=True)

            return res

    def get_data_from_file(self, filename: str) -> pd.DataFrame:
        # Method yield each dictionary one by one
        res = pd.DataFrame(columns=self.get_keys())
        file = open(filename, "r")

        # from first line we get the units and the price date. We just look at the date
        line = file.readline()
        matches = re.findall("\d\d/\d\d/\d\d\d\d", line)  # noqa: W605
        if not (len(matches) == 2):
            pass
        else:
            # The second date is the one we want
            date = dt.datetime.strptime(
                matches[1], AdjustmentPriceFileReader.__dateFormatInFile__
            ).date()

            # Process all the lines
            while line:
                # read following line
                line = file.readline()
                splits = line.split(sep=";")
                first_col = splits[0]

                if (
                    first_col
                    in AdjustmentPriceFileReader.__dic_static_concepts__.keys()
                ):
                    concept_type = AdjustmentPriceFileReader.__dic_static_concepts__[
                        first_col
                    ][0]

                    if concept_type in self.conceptsToLoad:
                        units = AdjustmentPriceFileReader.__dic_static_concepts__[
                            first_col
                        ][1]

                        dico = self._process_line(date=date, 
                                                  concept=concept_type, 
                                                  values=splits[1:], 
                                                  multiplier=units,
                                                  periods_per_hour_input=periods_per_hour_input)
                        res = pd.concat([res, pd.DataFrame([dico])], ignore_index=True)

            return res

    def _process_line(self, date: dt.date, concept: DataTypeInMarginalPriceFile, values: list, multiplier=1.0, periods_per_hour_input=4) -> dict:
        
        key_list = self.__key_list_retrieve__

        result = dict.fromkeys(self.get_keys())
        result[key_list[0]] = date
        result[key_list[1]] = str(concept)

        values_processed = self._process_list_step(
                                    old_list=values[:], 
                                    new_length=(len(values)-1) * self.__hourly_periods_output__ // periods_per_hour_input
                                    )

        nan_list = [np.nan] * (25 * self.__hourly_periods_output__ - len(values_processed))
        values_processed.extend(nan_list)

        for i, v in enumerate(values_processed, start=1):
            if i > 25 * self.__hourly_periods_output__:
                break # Jump if 25-hour day or spaces ..
            
            f = multiplier * v
            result[key_list[i + 1]] = f
            
        return result

    def _process_list_step(self, old_list: list, new_length: int) -> list:
        old_length = len(old_list) - 1
        new_list = []

        intermediate_list = [float(parse_decimal(v, locale=self.__localeInFile__)) for v in old_list[:old_length]]
        
        if old_length == new_length:
            for i in range(0, new_length):
                new_list.append(intermediate_list[i])
        
        elif old_length < new_length:
            for i in range(0, new_length):
                new_list.append(intermediate_list[(i * old_length) // new_length])
        
        elif old_length > new_length:
            intermediate_array = np.reshape(intermediate_list[:old_length], (-1, old_length // new_length))
            new_list = intermediate_array.mean(axis=1).tolist()
        
        return new_list
