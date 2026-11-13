# Fabric notebook source

# MARKDOWN ********************

# Silver load
#
# Same pattern as a Fabric silver notebook:
# 1. Read a Bronze table into df
# 2. Clean df with withColumn
# 3. Create the Delta table if it does not exist
# 4. Overwrite it
#
# Default lakehouse: lh_AdventureWorks_Silver
# Also attach: lh_AdventureWorks_Bronze
# Runtime: 2.0
# Run the cells from top to bottom.
#
# Each Bronze run replaces the data, so these cells overwrite the silver
# table. A merge that only inserts new rows would leave old rows stale.

# CELL ********************

from pyspark.sql.functions import col, lit, when, trim, row_number, coalesce
from pyspark.sql.functions import min as spark_min, max as spark_max, year, quarter, month, dayofmonth, dayofyear, dayofweek, weekofyear, date_format, date_add
from pyspark.sql.types import *
from pyspark.sql.window import Window
from delta.tables import *

BRONZE = "lh_AdventureWorks_Bronze"

spark.conf.set("spark.sql.parquet.vorder.default", "true")
spark.conf.set("spark.microsoft.delta.optimizeWrite.enabled", "true")
spark.conf.set("spark.native.enabled", "true")

spark.sql("CREATE SCHEMA IF NOT EXISTS cleansed")
spark.sql("CREATE SCHEMA IF NOT EXISTS etl")

# CELL ********************

# Read every address and attach the state and country names.
# Person and Store reuse this dataframe.

df = spark.read.table(BRONZE + ".Person.Address")

state = spark.read.table(BRONZE + ".Person.StateProvince").select(
    col("StateProvinceID"),
    col("StateProvinceCode"),
    col("CountryRegionCode"),
    col("StateProvinceName")
)
country = spark.read.table(BRONZE + ".Person.CountryRegion").select(
    col("CountryRegionCode"),
    col("CountryRegionName").alias("CountryName")
)

df = df.drop("rowguid", "ModifiedDate") \
    .join(state, "StateProvinceID", "left") \
    .join(country, "CountryRegionCode", "left")

address_df = df

# CELL ********************

# Date
# Build a calendar from the first order or movement date through the last.

order_dates = spark.read.table(BRONZE + ".Sales.SalesOrderHeader").select(col("OrderDate").cast(DateType()).alias("d"))
history_dates = spark.read.table(BRONZE + ".Production.TransactionHistory").select(col("TransactionDate").cast(DateType()).alias("d"))
archive_dates = spark.read.table(BRONZE + ".Production.TransactionHistoryArchive").select(col("TransactionDate").cast(DateType()).alias("d"))

bounds = order_dates.union(history_dates).union(archive_dates).agg(
    spark_min("d").alias("min_d"),
    spark_max("d").alias("max_d")
).collect()[0]

start = bounds["min_d"].replace(month=1, day=1)
end = bounds["max_d"].replace(month=12, day=31)

df = spark.range(0, (end - start).days + 1) \
    .select(date_add(lit(start), col("id").cast(IntegerType())).alias("FullDate")) \
    .withColumn("DateKey", date_format(col("FullDate"), "yyyyMMdd").cast(IntegerType())) \
    .withColumn("CalendarYear", year(col("FullDate"))) \
    .withColumn("Quarter", quarter(col("FullDate"))) \
    .withColumn("MonthNo", month(col("FullDate"))) \
    .withColumn("MonthName", date_format(col("FullDate"), "MMMM")) \
    .withColumn("WeekOfYear", weekofyear(col("FullDate"))) \
    .withColumn("DayOfMonth", dayofmonth(col("FullDate"))) \
    .withColumn("DayOfYear", dayofyear(col("FullDate"))) \
    .withColumn("DayOfWeekName", date_format(col("FullDate"), "EEEE")) \
    .withColumn("DayOfWeekNo", dayofweek(col("FullDate"))) \
    .withColumn("IsWeekend", dayofweek(col("FullDate")).isin(1, 7)) \
    .withColumn("IsWeekday", ~col("IsWeekend"))

DeltaTable.createIfNotExists(spark) \
    .tableName("cleansed.Date") \
    .addColumn("DateKey", IntegerType()) \
    .addColumn("FullDate", DateType()) \
    .addColumn("CalendarYear", IntegerType()) \
    .addColumn("Quarter", IntegerType()) \
    .addColumn("MonthNo", IntegerType()) \
    .addColumn("MonthName", StringType()) \
    .addColumn("WeekOfYear", IntegerType()) \
    .addColumn("DayOfMonth", IntegerType()) \
    .addColumn("DayOfYear", IntegerType()) \
    .addColumn("DayOfWeekName", StringType()) \
    .addColumn("DayOfWeekNo", IntegerType()) \
    .addColumn("IsWeekend", BooleanType()) \
    .addColumn("IsWeekday", BooleanType()) \
    .execute()

df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("cleansed.Date")
print("Date", df.count())

# CELL ********************

# SalesOrderHeader
# Tax and freight stay on the header in Silver. Gold splits them across lines.

df = spark.read.table(BRONZE + ".Sales.SalesOrderHeader")

df = df.drop("rowguid") \
    .withColumn("SubTotal", col("SubTotal").cast(DecimalType(19, 4))) \
    .withColumn("TaxAmt", col("TaxAmt").cast(DecimalType(19, 4))) \
    .withColumn("Freight", col("Freight").cast(DecimalType(19, 4))) \
    .withColumn("TotalDue", col("TotalDue").cast(DecimalType(19, 4)))

DeltaTable.createIfNotExists(spark) \
    .tableName("cleansed.SalesOrderHeader") \
    .addColumn("SalesOrderID", IntegerType()) \
    .addColumn("RevisionNumber", IntegerType()) \
    .addColumn("OrderDate", TimestampType()) \
    .addColumn("DueDate", TimestampType()) \
    .addColumn("ShipDate", TimestampType()) \
    .addColumn("Status", IntegerType()) \
    .addColumn("OnlineOrderFlag", BooleanType()) \
    .addColumn("SalesOrderNumber", StringType()) \
    .addColumn("PurchaseOrderNumber", StringType()) \
    .addColumn("AccountNumber", StringType()) \
    .addColumn("CustomerID", IntegerType()) \
    .addColumn("SalesPersonID", IntegerType()) \
    .addColumn("TerritoryID", IntegerType()) \
    .addColumn("BillToAddressID", IntegerType()) \
    .addColumn("ShipToAddressID", IntegerType()) \
    .addColumn("ShipMethodID", IntegerType()) \
    .addColumn("CreditCardID", IntegerType()) \
    .addColumn("CreditCardApprovalCode", StringType()) \
    .addColumn("CurrencyRateID", IntegerType()) \
    .addColumn("SubTotal", DecimalType(19, 4)) \
    .addColumn("TaxAmt", DecimalType(19, 4)) \
    .addColumn("Freight", DecimalType(19, 4)) \
    .addColumn("TotalDue", DecimalType(19, 4)) \
    .addColumn("Comment", StringType()) \
    .addColumn("ModifiedDate", TimestampType()) \
    .execute()

expected = spark.read.table(BRONZE + ".Sales.SalesOrderHeader").count()
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("cleansed.SalesOrderHeader")
print("SalesOrderHeader", expected, df.count())

# CELL ********************

# SalesOrderDetail
# SalesOrderDetailID is the line id.

df = spark.read.table(BRONZE + ".Sales.SalesOrderDetail")

df = df.drop("rowguid") \
    .withColumn("UnitPrice", col("UnitPrice").cast(DecimalType(19, 4))) \
    .withColumn("UnitPriceDiscount", col("UnitPriceDiscount").cast(DecimalType(19, 4))) \
    .withColumn("LineTotal", col("LineTotal").cast(DecimalType(19, 4)))

DeltaTable.createIfNotExists(spark) \
    .tableName("cleansed.SalesOrderDetail") \
    .addColumn("SalesOrderID", IntegerType()) \
    .addColumn("SalesOrderDetailID", IntegerType()) \
    .addColumn("CarrierTrackingNumber", StringType()) \
    .addColumn("OrderQty", IntegerType()) \
    .addColumn("ProductID", IntegerType()) \
    .addColumn("SpecialOfferID", IntegerType()) \
    .addColumn("UnitPrice", DecimalType(19, 4)) \
    .addColumn("UnitPriceDiscount", DecimalType(19, 4)) \
    .addColumn("LineTotal", DecimalType(19, 4)) \
    .addColumn("ModifiedDate", TimestampType()) \
    .execute()

expected = spark.read.table(BRONZE + ".Sales.SalesOrderDetail").count()
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("cleansed.SalesOrderDetail")
print("SalesOrderDetail", expected, df.count())

# CELL ********************

# Customer
# Keys only. The name is on Person. The store address is on Store.

df = spark.read.table(BRONZE + ".Sales.Customer")

df = df.drop("rowguid", "ModifiedDate") \
    .select("CustomerID", "PersonID", "StoreID", "TerritoryID", "AccountNumber")

DeltaTable.createIfNotExists(spark) \
    .tableName("cleansed.Customer") \
    .addColumn("CustomerID", IntegerType()) \
    .addColumn("PersonID", IntegerType()) \
    .addColumn("StoreID", IntegerType()) \
    .addColumn("TerritoryID", IntegerType()) \
    .addColumn("AccountNumber", StringType()) \
    .execute()

expected = spark.read.table(BRONZE + ".Sales.Customer").count()
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("cleansed.Customer")
print("Customer", expected, df.count())

# CELL ********************

# SalesTerritory

df = spark.read.table(BRONZE + ".Sales.SalesTerritory")

df = df.drop("rowguid", "ModifiedDate") \
    .select(
        col("TerritoryID"),
        col("SalesTerritoryName").alias("TerritoryName"),
        col("CountryRegionCode"),
        col("Group").alias("TerritoryGroup")
    )

DeltaTable.createIfNotExists(spark) \
    .tableName("cleansed.SalesTerritory") \
    .addColumn("TerritoryID", IntegerType()) \
    .addColumn("TerritoryName", StringType()) \
    .addColumn("CountryRegionCode", StringType()) \
    .addColumn("TerritoryGroup", StringType()) \
    .execute()

expected = spark.read.table(BRONZE + ".Sales.SalesTerritory").count()
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("cleansed.SalesTerritory")
print("SalesTerritory", expected, df.count())

# CELL ********************

# Person
# One email, one phone, and one address per person.
# Address order: Primary, Home, Billing, Shipping.
# Blank text becomes Unknown.

person = spark.read.table(BRONZE + ".Person.Person") \
    .drop("rowguid", "ModifiedDate", "AdditionalContactInfo", "Demographics", "EmailPromotion", "NameStyle") \
    .select("BusinessEntityID", "PersonType", "Title", "FirstName", "MiddleName", "LastName", "Suffix")

email = spark.read.table(BRONZE + ".Person.EmailAddress").drop("rowguid", "ModifiedDate")
email_window = Window.partitionBy("BusinessEntityID").orderBy(col("EmailAddressID"))
email = email.withColumn("_rn", row_number().over(email_window)).filter(col("_rn") == 1).select("BusinessEntityID", "EmailAddress")

phone = spark.read.table(BRONZE + ".Person.PersonPhone").drop("ModifiedDate")
phone_type = spark.read.table(BRONZE + ".Person.PhoneNumberType").drop("ModifiedDate") \
    .select(col("PhoneNumberTypeID"), col("PhoneNumberTypeName").alias("PhoneNumberType"))
phone = phone.join(phone_type, "PhoneNumberTypeID", "left")
phone_window = Window.partitionBy("BusinessEntityID").orderBy(col("PhoneNumberTypeID"), col("PhoneNumber"))
phone = phone.withColumn("_rn", row_number().over(phone_window)).filter(col("_rn") == 1) \
    .select("BusinessEntityID", "PhoneNumber", "PhoneNumberType")

link = spark.read.table(BRONZE + ".Person.BusinessEntityAddress").drop("rowguid", "ModifiedDate")
addr_type = spark.read.table(BRONZE + ".Person.AddressType").drop("rowguid", "ModifiedDate") \
    .select(col("AddressTypeID"), col("AddressTypeName"))
link = link.join(addr_type, "AddressTypeID", "left") \
    .withColumn("AddressPriority",
        when(col("AddressTypeName") == "Primary", lit(1))
        .when(col("AddressTypeName") == "Home", lit(2))
        .when(col("AddressTypeName") == "Billing", lit(3))
        .when(col("AddressTypeName") == "Shipping", lit(4))
        .otherwise(lit(9))
    )
link_window = Window.partitionBy("BusinessEntityID").orderBy(col("AddressPriority"), col("AddressID"))
link = link.withColumn("_rn", row_number().over(link_window)).filter(col("_rn") == 1) \
    .select("BusinessEntityID", "AddressID")

df = person.join(email, "BusinessEntityID", "left") \
    .join(phone, "BusinessEntityID", "left") \
    .join(link, "BusinessEntityID", "left") \
    .join(address_df.drop("StateProvinceID"), "AddressID", "left")

text_columns = [
    "Title", "FirstName", "MiddleName", "LastName", "Suffix",
    "EmailAddress", "PhoneNumber", "PhoneNumberType",
    "AddressLine1", "AddressLine2", "City", "StateProvinceCode",
    "StateProvinceName", "PostalCode", "CountryRegionCode", "CountryName",
    "SpatialLocation"
]
for name in text_columns:
    df = df.withColumn(name, when(col(name).isNull() | (col(name) == ""), lit("Unknown")).otherwise(col(name)))

df = df.drop("AddressID")

DeltaTable.createIfNotExists(spark) \
    .tableName("cleansed.Person") \
    .addColumn("BusinessEntityID", IntegerType()) \
    .addColumn("PersonType", StringType()) \
    .addColumn("Title", StringType()) \
    .addColumn("FirstName", StringType()) \
    .addColumn("MiddleName", StringType()) \
    .addColumn("LastName", StringType()) \
    .addColumn("Suffix", StringType()) \
    .addColumn("EmailAddress", StringType()) \
    .addColumn("PhoneNumber", StringType()) \
    .addColumn("PhoneNumberType", StringType()) \
    .addColumn("AddressLine1", StringType()) \
    .addColumn("AddressLine2", StringType()) \
    .addColumn("City", StringType()) \
    .addColumn("StateProvinceCode", StringType()) \
    .addColumn("StateProvinceName", StringType()) \
    .addColumn("PostalCode", StringType()) \
    .addColumn("CountryRegionCode", StringType()) \
    .addColumn("CountryName", StringType()) \
    .addColumn("SpatialLocation", StringType()) \
    .execute()

expected = spark.read.table(BRONZE + ".Person.Person").count()
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("cleansed.Person")
print("Person", expected, df.count())

# CELL ********************

# Store
# Address type 3 is Main Office. Every store has one.

store = spark.read.table(BRONZE + ".Sales.Store") \
    .drop("rowguid", "ModifiedDate", "Demographics", "SalesPersonID") \
    .select(col("BusinessEntityID").alias("StoreID"), col("StoreName"))

link = spark.read.table(BRONZE + ".Person.BusinessEntityAddress") \
    .filter(col("AddressTypeID") == 3) \
    .select(col("BusinessEntityID").alias("StoreID"), col("AddressID"))
link_window = Window.partitionBy("StoreID").orderBy(col("AddressID"))
link = link.withColumn("_rn", row_number().over(link_window)).filter(col("_rn") == 1).drop("_rn")

store_address = address_df.drop("StateProvinceID", "SpatialLocation")
if "SpatialLocationSrid" in store_address.columns:
    store_address = store_address.drop("SpatialLocationSrid")

df = store.join(link, "StoreID", "left").join(store_address, "AddressID", "left").drop("AddressID")

text_columns = [
    "StoreName", "AddressLine1", "AddressLine2", "City",
    "StateProvinceCode", "StateProvinceName", "PostalCode",
    "CountryRegionCode", "CountryName"
]
for name in text_columns:
    df = df.withColumn(name, when(col(name).isNull() | (col(name) == ""), lit("Unknown")).otherwise(col(name)))

DeltaTable.createIfNotExists(spark) \
    .tableName("cleansed.Store") \
    .addColumn("StoreID", IntegerType()) \
    .addColumn("StoreName", StringType()) \
    .addColumn("AddressLine1", StringType()) \
    .addColumn("AddressLine2", StringType()) \
    .addColumn("City", StringType()) \
    .addColumn("StateProvinceCode", StringType()) \
    .addColumn("StateProvinceName", StringType()) \
    .addColumn("PostalCode", StringType()) \
    .addColumn("CountryRegionCode", StringType()) \
    .addColumn("CountryName", StringType()) \
    .execute()

expected = spark.read.table(BRONZE + ".Sales.Store").count()
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("cleansed.Store")
print("Store", expected, df.count())

# CELL ********************

# Product
# Category, subcategory, and the size and weight unit names are joined on.

product = spark.read.table(BRONZE + ".Production.Product").drop("rowguid") \
    .withColumnRenamed("ProductName", "Name")
subcategory = spark.read.table(BRONZE + ".Production.ProductSubcategory").drop("rowguid", "ModifiedDate") \
    .select("ProductSubcategoryID", "ProductCategoryID", col("ProductSubcategoryName").alias("Subcategory"))
category = spark.read.table(BRONZE + ".Production.ProductCategory").drop("rowguid", "ModifiedDate") \
    .select("ProductCategoryID", col("ProductCategoryName").alias("Category"))
unit = spark.read.table(BRONZE + ".Production.UnitMeasure").drop("ModifiedDate") \
    .select("UnitMeasureCode", col("UnitMeasureName").alias("UnitName"))

df = product.join(subcategory, "ProductSubcategoryID", "left") \
    .join(category, "ProductCategoryID", "left") \
    .join(unit.select(col("UnitMeasureCode").alias("SizeUnitMeasureCode"), col("UnitName").alias("SizeUnit")), "SizeUnitMeasureCode", "left") \
    .join(unit.select(col("UnitMeasureCode").alias("WeightUnitMeasureCode"), col("UnitName").alias("WeightUnit")), "WeightUnitMeasureCode", "left") \
    .withColumn("Discontinued", col("DiscontinuedDate").isNotNull()) \
    .withColumn("StandardCost", col("StandardCost").cast(DecimalType(19, 4))) \
    .withColumn("ListPrice", col("ListPrice").cast(DecimalType(19, 4))) \
    .select(
        "ProductID", "Name", "ProductNumber", "Color", "Category", "Subcategory",
        "Size", "Weight", "SizeUnit", "WeightUnit", "Class", "Style",
        "StandardCost", "ListPrice", "Discontinued", "DiscontinuedDate", "ModifiedDate"
    )

text_columns = ["Name", "Color", "Size", "Class", "Style", "Category", "Subcategory", "SizeUnit", "WeightUnit"]
for name in text_columns:
    df = df.withColumn(name, when(col(name).isNull() | (col(name) == ""), lit("Unknown")).otherwise(col(name)))

DeltaTable.createIfNotExists(spark) \
    .tableName("cleansed.Product") \
    .addColumn("ProductID", IntegerType()) \
    .addColumn("Name", StringType()) \
    .addColumn("ProductNumber", StringType()) \
    .addColumn("Color", StringType()) \
    .addColumn("Category", StringType()) \
    .addColumn("Subcategory", StringType()) \
    .addColumn("Size", StringType()) \
    .addColumn("Weight", DecimalType(8, 2)) \
    .addColumn("SizeUnit", StringType()) \
    .addColumn("WeightUnit", StringType()) \
    .addColumn("Class", StringType()) \
    .addColumn("Style", StringType()) \
    .addColumn("StandardCost", DecimalType(19, 4)) \
    .addColumn("ListPrice", DecimalType(19, 4)) \
    .addColumn("Discontinued", BooleanType()) \
    .addColumn("DiscontinuedDate", TimestampType()) \
    .addColumn("ModifiedDate", TimestampType()) \
    .execute()

expected = spark.read.table(BRONZE + ".Production.Product").count()
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("cleansed.Product")
print("Product", expected, df.count())

# CELL ********************

# ProductCostHistory
# The standard cost in effect between StartDate and EndDate.

df = spark.read.table(BRONZE + ".Production.ProductCostHistory")

df = df.drop("ModifiedDate") \
    .withColumn("StartDate", col("StartDate").cast(DateType())) \
    .withColumn("EndDate", col("EndDate").cast(DateType())) \
    .withColumn("StandardCost", col("StandardCost").cast(DecimalType(19, 4)))

DeltaTable.createIfNotExists(spark) \
    .tableName("cleansed.ProductCostHistory") \
    .addColumn("ProductID", IntegerType()) \
    .addColumn("StartDate", DateType()) \
    .addColumn("EndDate", DateType()) \
    .addColumn("StandardCost", DecimalType(19, 4)) \
    .execute()

expected = spark.read.table(BRONZE + ".Production.ProductCostHistory").count()
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("cleansed.ProductCostHistory")
print("ProductCostHistory", expected, df.count())

# CELL ********************

# Inventory movement
# P = purchase, W = work order, S = sale.
# Gold ignores W when it builds FactStock.

columns = [
    "TransactionID", "ProductID", "ReferenceOrderID", "ReferenceOrderLineID",
    "TransactionDate", "TransactionType", "Quantity", "ActualCost"
]
history = spark.read.table(BRONZE + ".Production.TransactionHistory").select(*columns) \
    .withColumn("SourceTable", lit("TransactionHistory"))
archive = spark.read.table(BRONZE + ".Production.TransactionHistoryArchive").select(*columns) \
    .withColumn("SourceTable", lit("TransactionHistoryArchive"))

df = history.unionByName(archive) \
    .withColumn("TransactionID", col("TransactionID").cast(LongType())) \
    .withColumn("ProductID", col("ProductID").cast(IntegerType())) \
    .withColumn("ReferenceOrderID", col("ReferenceOrderID").cast(IntegerType())) \
    .withColumn("ReferenceOrderLineID", col("ReferenceOrderLineID").cast(IntegerType())) \
    .withColumn("TransactionDate", col("TransactionDate").cast(TimestampType())) \
    .withColumn("TransactionType", trim(col("TransactionType"))) \
    .withColumn("Quantity", col("Quantity").cast(IntegerType())) \
    .withColumn("ActualCost", col("ActualCost").cast(DecimalType(19, 4)))

DeltaTable.createIfNotExists(spark) \
    .tableName("cleansed.InventoryMovement") \
    .addColumn("TransactionID", LongType()) \
    .addColumn("ProductID", IntegerType()) \
    .addColumn("ReferenceOrderID", IntegerType()) \
    .addColumn("ReferenceOrderLineID", IntegerType()) \
    .addColumn("TransactionDate", TimestampType()) \
    .addColumn("TransactionType", StringType()) \
    .addColumn("Quantity", IntegerType()) \
    .addColumn("ActualCost", DecimalType(19, 4)) \
    .addColumn("SourceTable", StringType()) \
    .execute()

expected = spark.read.table(BRONZE + ".Production.TransactionHistory").count() \
    + spark.read.table(BRONZE + ".Production.TransactionHistoryArchive").count()
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("cleansed.InventoryMovement")
print("InventoryMovement", expected, df.count())

# CELL ********************

# Check
# The printed pairs must match. Date has no Bronze twin, so any count above zero is enough.

checks = [
    ("SalesOrderHeader", spark.read.table(BRONZE + ".Sales.SalesOrderHeader").count()),
    ("SalesOrderDetail", spark.read.table(BRONZE + ".Sales.SalesOrderDetail").count()),
    ("Customer", spark.read.table(BRONZE + ".Sales.Customer").count()),
    ("SalesTerritory", spark.read.table(BRONZE + ".Sales.SalesTerritory").count()),
    ("Person", spark.read.table(BRONZE + ".Person.Person").count()),
    ("Store", spark.read.table(BRONZE + ".Sales.Store").count()),
    ("Product", spark.read.table(BRONZE + ".Production.Product").count()),
    ("ProductCostHistory", spark.read.table(BRONZE + ".Production.ProductCostHistory").count()),
    ("InventoryMovement", spark.read.table(BRONZE + ".Production.TransactionHistory").count()
        + spark.read.table(BRONZE + ".Production.TransactionHistoryArchive").count()),
]

failed = []
for table_name, expected_count in checks:
    actual_count = spark.read.table("cleansed." + table_name).count()
    print(table_name, expected_count, actual_count)
    if actual_count != expected_count:
        failed.append(table_name)

date_count = spark.read.table("cleansed.Date").count()
print("Date", date_count)
if date_count == 0:
    failed.append("Date")

if failed:
    raise RuntimeError("Silver check failed: " + ", ".join(failed))

print("Silver load passed.")
