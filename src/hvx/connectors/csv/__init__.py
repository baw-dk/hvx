# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
CSV Ingestion Module

Loads building environmental data from CSV files and creates
MeteringPoint and TimeSeries objects following the core models.
"""

from .data_loader import CSVDataLoader, load_from_csv, load_portfolio_from_csv
from .portfolio_loader import (
    PortfolioLoader,
    load_portfolio,
    load_hoeje_taastrup,
    load_dummy_data,
    PortfolioLoadResult,
)

__all__ = [
    "CSVDataLoader",
    "load_from_csv",
    "load_portfolio_from_csv",
    "PortfolioLoader",
    "load_portfolio",
    "load_hoeje_taastrup",
    "load_dummy_data",
    "PortfolioLoadResult",
]
