import os
from dotenv import load_dotenv
from pyspark.sql import SparkSession
from pyspark.sql.types import *
from pyspark.sql.functions import *
from Code.transform import TransformData


class LoadData:
    def __init__(self, trend_type):
        load_dotenv()
        self.basedir = "/Users/abhishekteli/Documents/Projects/StockDataAnalysis/checkpoint/"
        self.trend_type = trend_type
        self.bootstrap_server = 'localhost:9092'

        #--------------------------------#
        if self.trend_type == "GAINERS":
            self.topic = 'Gainers'
        elif self.trend_type == 'LOSERS':
            self.topic = 'Losers'
        else:
            self.topic = 'Active'
        #--------------------------------#

        self.spark = (SparkSession.builder
                      .master('local[3]')
                      .appName('RealStockData')
                      .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.1.2,"
                                                     "org.postgresql:postgresql:42.2.5")
                      .getOrCreate()
                      )
        #--------------------------------------------#
        if self.trend_type == "GAINERS":
            self.checkpnt = f"{self.basedir}/Gainers/"
        elif self.trend_type == "LOSERS":
            self.checkpnt = f"{self.basedir}/Losers/"
        else:
            self.checkpnt = f"{self.basedir}/Active/"
        #--------------------------------------------#

        self.spark.sparkContext.setLogLevel('Error')

    def getSchema(self):
        schema = (StructType([
            StructField("symbol", StringType(), False),
            StructField("type", StringType(), True),
            StructField("name", StringType(), False),
            StructField("price", FloatType(), False),
            StructField("change", FloatType(), True),
            StructField("change_percent", FloatType(), True),
            StructField("previous_close", FloatType(), True),
            StructField("pre_or_post_market", FloatType(), True),
            StructField("pre_or_post_market_change", FloatType(), True),
            StructField("pre_or_pos_market_change_percent", FloatType(), True),
            StructField("last_update_utc", TimestampType(), True),
            StructField("currency", StringType(), True),
            StructField("exchange", StringType(), True),
            StructField("exchange_open", TimestampType(), True),
            StructField("exchange_close", TimestampType(), True),
            StructField("timezone", StringType(), True),
            StructField("utc_offset_sec", IntegerType(), True),
            StructField("country_code", StringType(), True),
            StructField("google_mid", StringType(), True)
        ]))

        return schema

    def readData(self):
        return (
            self.spark.readStream
            .format("kafka")
            .option("kafka.bootstrap.servers", f"{self.bootstrap_server}")
            .option("subscribe", f"{self.topic}")
            .option("startingOffsets", "earliest")
            .load()
        )

    def getStockData(self, kafka_df):
        schema = self.getSchema()
        json_df = kafka_df.withColumn("json_array", from_json(col("value").cast("string"), ArrayType(schema))) \
            .withColumn("status", col('key').cast("string"))
        exploded_df = json_df.withColumn("data", explode(col("json_array"))).select("data.*", "status")
        return exploded_df

    def saveToDatabase(self, result_df, batch_id):
        url = 'jdbc:postgresql://localhost:5432/realstockdata'
        properties = {
            "user": os.getenv('USERNAME'),
            "password": os.getenv('DATABASE_PASSWORD'),
            "driver": 'org.postgresql.Driver'
        }
        try:
            result_df.write.jdbc(url=url, table='stock', mode='append', properties=properties)
        except Exception as e:
            print(' ')

    def writeToDatabase(self, stockdata_df):
        sQuery = (
            stockdata_df.writeStream
            .format('console')
            .foreachBatch(self.saveToDatabase)
            .option("checkpointLocation", f"{self.checkpnt}")
            .outputMode('update')
            .start()
        )
        return sQuery

    def process(self):
        tr = TransformData()
        kafka_df = self.readData()
        parsed_df = self.getStockData(kafka_df)
        stockData_df = tr.process(parsed_df)
        sQuery = self.writeToDatabase(stockData_df)
        return sQuery
