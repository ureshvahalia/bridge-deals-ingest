from __future__ import annotations
import polars as pl
import xlsxwriter
from typing import Optional, Dict, Type
from pathlib import Path
from logging import getLogger
from enum import Enum

logger = getLogger(__name__)

class DBType(Enum):
    CSV     = "csv"
    PARQUET = "parquet"
    XLS     = "xlsx"
    SQLITE  = "sqlite"
    
class BridgeDB:
    """Base class for bridge database manager"""
    _registry: Dict[DBType, Type["BridgeDB"]] = {}

    def __init__(self, path: Optional[Path] = None):
        self.locn = Path(path if path else ".")
        if self.locn.exists():
            if not self.locn.is_dir():
                raise FileExistsError(f"Path '{self.locn}' exists and is not a directory")
        else:
            self.locn.mkdir(parents=True, exist_ok=False)
        self.components: Dict[str, DBComp] = {}
        self.dbExt: str = ""
        self.base_name: str = ""

    @classmethod
    def register(cls, db_type: DBType):
        """Decorator for subclasses to register themselves."""
        def decorator(subclass: Type["BridgeDB"]):
            cls._registry[db_type] = subclass
            return subclass
        return decorator

    @classmethod
    def create(cls, db_type: DBType, path: Path) -> "BridgeDB":
        """Factory method to create an instance based on the DBType."""
        if db_type not in cls._registry:
            raise ValueError(f"Unsupported DB type: {db_type}")
        return cls._registry[db_type](path)

    def addComponent(self, name: str, comp: "DBComp") -> None:
        self.components[name] = comp

    def makeFname(self, name: str) -> Path:
        return self.locn / f"{name}{self.dbExt}"

    def readDf(self, fname: Path) -> pl.DataFrame:
        raise NotImplementedError("This method should be implemented in subclasses")

    def writeDf(self, df: pl.DataFrame, name: str, **kwargs) -> None:
        raise NotImplementedError("This method should be implemented in subclasses")
    
    def getWorkbook(self) -> xlsxwriter.Workbook:
        raise NotImplementedError("This method should be implemented in subclasses")
    
    def close(self) -> None:
        return

@BridgeDB.register(DBType.CSV)
class CsvBridgeDB(BridgeDB):
    """CSV-specific functionality"""
    def __init__(self, path: Optional[Path] = None, base_name: Optional[str] = None):
        super().__init__(path)  # ignore the base_name
        self.dbExt = ".csv"

    def readDf(self, fname: Path) -> pl.DataFrame:
        return pl.read_csv(fname)

    def writeDf(self, df: pl.DataFrame, name: str, **kwargs) -> None:
        df.write_csv(super().makeFname(name))

@BridgeDB.register(DBType.XLS)
class XlsBridgeDB(BridgeDB):
    """XLS-specific functionality"""
    def __init__(self, path: Optional[Path] = None, base_name: Optional[str] = None):
        super().__init__(path)
        self.dbExt = ".xlsx"
        base_name = base_name if base_name is not None else "Master"
        self.workbook = xlsxwriter.Workbook(self.locn / f"{base_name}.xlsx")

    def readDf(self, fname: Path) -> pl.DataFrame:
        return pl.read_excel(fname)

    def writeDf(self, df: pl.DataFrame, name: str, **kwargs) -> None:
        df.write_excel(workbook=self.workbook, worksheet=name, **kwargs)
        
    def close(self) -> None:
        self.workbook.close()

@BridgeDB.register(DBType.PARQUET)
class ParquetBridgeDB(BridgeDB):
    """Parquet-specific functionality"""
    def __init__(self, path: Optional[Path] = None, base_name: Optional[str] = None):
        super().__init__(path)  # ignore the base_name
        self.dbExt = ".parquet"

    def readDf(self, fname: Path) -> pl.DataFrame:
        return pl.read_parquet(fname)

    def writeDf(self, df: pl.DataFrame, name: str, **kwargs) -> None:
        df.write_parquet(super().makeFname(name), **kwargs)

import threading
class DBComp:
    """Base class for bridge database components"""
    def __init__(self, db: BridgeDB, fileNameBase: str, pkey: str, schema: Dict[str, type]):
        self.db = db
        self.base_name = fileNameBase
        self.fname: Path = self.db.makeFname(fileNameBase)
        self.SCHEMA = schema
        self.df = self._initialize_dataframe()
        self.maxId: int = int(self.df[pkey].max() or 0)  # type: ignore
        self._id_lock = threading.Lock()
        
    def _initialize_dataframe(self) -> pl.DataFrame:
        """Initialize the DataFrame with proper schema."""
        try:
            if self.fname.is_file():
                df = self.db.readDf(self.fname)
                if set(df.schema.keys()) != set(self.SCHEMA.keys()):
                    raise ValueError(f"Invalid schema in {self.fname}. Expected {self.SCHEMA}")
                return df
            return pl.DataFrame(schema=self.SCHEMA)
        except Exception as e:
            logger.error(f"Error initializing database: {str(e)}")
            raise

    def incrementMaxId(self) -> int:
        # Increment the maximum ID value and return the new ID
        # with self._id_lock:  # Use the lock when incrementing the ID
            self.maxId = self.maxId + 1
            return self.maxId

    def sync(self) -> None:
        """Save the current DataFrame to disk."""
        try:
            self.db.writeDf(self.df, self.base_name)
        except Exception as e:
            logger.error(f"Error saving to disk: {str(e)}")
            raise
