# AGENTS.md: AdventureWorks2025 Medallion Project

Read this file first, then the extracts in `docs/source/`.

## 1. Project summary

Medallion project on a Fabric trial capacity. The source is AdventureWorks2025 on SQL Server 2025, through the on-premises data gateway. Do not load `AdventureWorksDW2025`. Do not restore the OLTP database. Database CDC stays enabled and no table is captured.

```
SQL Server 2025 -> gateway -> lh_AdventureWorks_Bronze (69 raw Delta tables)
                           -> lh_AdventureWorks_Silver (cleansed schema, Gold inputs only)
                           -> wh_AdventureWorks_Gold   (FactSales, FactStock, dimensions)
                           -> Power BI semantic model (Direct Lake on OneLake)
```

Spark cleans. The warehouse loads Gold in one transaction.

## 2. Source of truth

- `docs/source/adventure_works.txt`: OLTP tables, keys, foreign keys, row counts
- `docs/source/adventure_works_dw.txt`: warehouse extract kept for reference only
- `docs/decisions.md`: decision log
- `docs/part1-architecture.md`: architecture

Never invent a table or column. This OLTP has 121,317 order lines.

Banned names: `Person.Contact`, `Sales.Individual`, `CustomerAddress`, `EmployeeAddress`, `StoreContact`, `VendorContact`, `ContactCreditCard`, `Employee.ManagerID`, `Sales.Customer.CustomerType`.

## 3. Naming

| Item | Name |
|---|---|
| Lakehouses | `lh_AdventureWorks_Bronze`, `lh_AdventureWorks_Silver` |
| Warehouse | `wh_AdventureWorks_Gold` |
| Silver entities | `cleansed.<Entity>` |
| Silver logs | `etl.quarantine`, `etl.dq_result`, `etl.load_log` |
| Gold facts | `FactSales`, `FactStock` |
| Gold dimensions | `DimDate`, `DimCustomer`, `DimStore`, `DimProduct` |
| Surrogate | `<Entity>Key`. Business keys keep the source name |
| Audit | `dbo.ETL_Log` |
| Watermark | `dbo.ingest_watermark` |
| Load | `dbo.usp_Load_Gold` |

No `Silver_` prefix. No `DimLocation`.

## 4. Bronze

Raw landing. Source schema and table names. The control query is `sql/source/ingest_control.sql`. It is read-only. `fabric_user` stays `db_datareader`.

Excluded: the `cdc` schema, `dbo.AWBuildVersion`, `dbo.sysdiagrams`, `dbo.systranschemas`, `Person.Password`, and views.

Type serialization in that query: geography to WKT plus SRID, `hierarchyid` to string, `xml` to `nvarchar(max)`, alias types cast from `sys.types`, `varbinary` / `binary` / `image` omitted.

`is_core = 1` includes `Production.TransactionHistory` and `Production.TransactionHistoryArchive`. `ProductInventory` is copied and is not core.

Default load is full overwrite. Incremental upsert is only `Sales.SalesOrderHeader` and `Sales.SalesOrderDetail`.

Never put credentials in code or docs.

## 5. Silver

One Fabric Runtime 2.0 notebook. Read Bronze, write `cleansed` tables for Gold inputs only.

`FactSales` line id is `SalesOrderDetailID`. Do not replace it with a `tinyint` sequence.

Drop `rowguid` and `ModifiedDate`, except `ModifiedDate` on the two watermark tables and the product `ModifiedDate` kept on `DimProduct`. Drop `CardNumber`, `NationalIDNumber`, `LoginID`, and `BirthDate` if those columns are read.

Money is `DecimalType(19,4)`. Nulls use a documented default. Do not drop rows silently. Rejects go to `etl.quarantine`.

Person address priority is Primary, then Home, then Billing, then Shipping. Tie-break `AddressID`. Store address is `AddressTypeID` 3 (Main Office) only.

V-Order on. No partitioning, Z-order, or liquid clustering.

## 6. Gold

`dbo.usp_Load_Gold` is one transaction. Keys are declared `NOT ENFORCED`. Unknown member is `-1`.

`FactSales` is one row per order line. `GrossSalesAmount = UnitPrice * Qty`. `DiscountAmount = GrossSalesAmount * UnitPriceDiscount`; the discount is a rate. `LineNetSalesAmount = GrossSalesAmount - DiscountAmount`, and the total-sales measure is `SUM(LineNetSalesAmount)`. `AllocatedTaxAmount` and `AllocatedFreightAmount` are allocated by the line's share of header `SubTotal`. `LineTotalDueAmount = LineNetSalesAmount + AllocatedTaxAmount + AllocatedFreightAmount`. `UnitStandardCost` is `ProductCostHistory` as of `OrderDate`, else `Product.StandardCost`; `LineCostAmount = UnitStandardCost * Qty`; `ProfitAmount = LineNetSalesAmount - LineCostAmount`. A zero subtotal keeps both allocations on the first line.

`DimCustomer` is a person. `DimStore` is a store. Store-only lines use customer `-1`. Person-only lines use store `-1`.

`FactStock` is one row per product per day from both transaction tables. Ignore `TransactionType = W`.

- `PurchaseQty` = `P` on that day
- `SalesQty` = `S` on that day
- `OpeningQty` = purchases minus sales before that day. The first day opens at 0.
- `ClosingQty` = `OpeningQty + PurchaseQty - SalesQty`

Do not sum opening or closing across days. Opening for a period is `OpeningQty` on the first selected date. Closing is opening plus the period's purchases minus the period's sales.

`FactStock` is not the shelf quantity. Do not read `ProductInventory` into it. Do not call opening or closing the quantity on the shelf. There is no `DimLocation`.

## 7. Trial

One Spark notebook per pipeline run. Runtime 2.0. Starter pool. No custom warm pool. Copy batch count 4. Do not schedule the pipeline. Dataflow Gen2 is not used.
