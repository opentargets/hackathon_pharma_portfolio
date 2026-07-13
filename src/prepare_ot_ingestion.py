"""Prepare Open Targets ingestion file from pharma portfolio data.

Concatenates all 20 pharma pipeline parquet files, maps drug names -> ChEMBL IDs
and indications -> EFO IDs using OnToma, and outputs a single enriched parquet.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

import polars as pl
import pyspark.sql.functions as f
import sparknlp
from loguru import logger
from ontoma import OnToma, OpenTargetsDisease, OpenTargetsDrug
from ontoma.ner._pipelines import get_device
from ontoma.ner.disease import extract_disease_entities
from ontoma.ner.drug import extract_drug_entities
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import (
    BooleanType,
    DateType,
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT.parent / "data"

DISEASE_INDEX_PATH = Path.home() / "EBI/repos/pipeline_work/output/disease"
DRUG_INDEX_PATH = Path.home() / "EBI/repos/pipeline_work/intermediate/chembl_molecule"

NER_DRUG_CACHE_PATH = ".cache/ner/pharma_drug.parquet"
NER_DISEASE_CACHE_PATH = ".cache/ner/pharma_disease.parquet"
NER_BATCH_SIZE = 256

logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    format="{time:HH:mm:ss} | {level:<7} | {message}",
)


# ── Todo 2: Data loading ──────────────────────────────────────────────


def load_all_pipelines() -> pl.DataFrame:
    """Glob all *_pipeline.parquet files and concatenate diagonally.

    Some files store columns with incompatible types (Null vs String,
    Date vs String, etc.) — cast to a common schema before merging.
    """
    pattern = str(ROOT / "pharmas" / "*" / "*_pipeline.parquet")
    fnames = sorted(glob.glob(pattern))
    logger.info(f"found {len(fnames)} pipeline parquet files")
    dfs = []
    for f in fnames:
        df = pl.read_parquet(f)
        unify = []
        for col in df.columns:
            t = df.schema[col]
            if t == pl.Null:
                if col == "synonyms":
                    unify.append(pl.lit(None).cast(pl.List(pl.String)).alias(col))
                else:
                    unify.append(pl.lit(None).cast(pl.String).alias(col))
            elif col == "extraction_date":
                unify.append(pl.col(col).cast(pl.String))
        if unify:
            df = df.with_columns(*unify)
        dfs.append(df)
    merged = pl.concat(dfs, how="diagonal")
    logger.info(f"merged {len(merged)} rows, {len(merged.columns)} columns")
    return merged


# ── Todo 3: Spark session factory ─────────────────────────────────────


def create_spark() -> SparkSession:
    """SparkSession with Kryo serialization and MPS awareness."""
    active = SparkSession.getActiveSession()
    if active is not None:
        active.stop()
    params = {
        "spark.driver.memory": "10g",
        "spark.driver.maxResultSize": "4g",
        "spark.serializer": "org.apache.spark.serializer.KryoSerializer",
        "spark.kryoserializer.buffer.max": "512m",
        "spark.sql.shuffle.partitions": "50",
        "spark.default.parallelism": "4",
        "spark.sql.adaptive.enabled": "true",
        "spark.ui.enabled": "false",
    }
    is_apple_silicon = get_device() == "mps"
    return sparknlp.start(params=params, apple_silicon=is_apple_silicon)


# ── Helper: Polars -> Spark conversion ─────────────────────────────────


def _polars_to_spark_type(pl_type):
    type_map = {
        pl.String: StringType(),
        pl.Int32: IntegerType(),
        pl.Int64: LongType(),
        pl.Float64: DoubleType(),
        pl.Boolean: BooleanType(),
        pl.Date: DateType(),
        pl.Datetime: TimestampType(),
    }
    return type_map.get(pl_type, StringType())


def _convert_to_spark(
    polars_df: pl.DataFrame, spark: SparkSession, chunk_size: int = 100000
) -> DataFrame:
    spark_schema = StructType(
        [
            StructField(name, _polars_to_spark_type(dtype), True)
            for name, dtype in polars_df.schema.items()
        ]
    )
    total = len(polars_df)
    if total <= chunk_size:
        return spark.createDataFrame(polars_df.to_pandas(), schema=spark_schema)
    chunks = []
    for i in range(0, total, chunk_size):
        c = polars_df.slice(i, chunk_size)
        chunks.append(spark.createDataFrame(c.to_pandas(), schema=spark_schema))
    result = chunks[0]
    for c in chunks[1:]:
        result = result.union(c)
    optimal = min(max(total // 50000, 8), 400)
    return result.repartition(optimal)


# ── Todo 4: Index loading ─────────────────────────────────────────────


def load_disease_index(spark: SparkSession) -> DataFrame:
    path = str(DISEASE_INDEX_PATH)
    logger.info(f"loading disease index from {path}")
    return spark.read.parquet(path)


def load_drug_index(spark: SparkSession) -> DataFrame:
    path = str(DRUG_INDEX_PATH)
    logger.info(f"loading drug index from {path}")
    return spark.read.parquet(path)


# ── Todo 5: Disease mapping ───────────────────────────────────────────


def map_diseases(
    df: pl.DataFrame, spark: SparkSession, disease_index: DataFrame,
    ner_extract_disease: bool = True,
) -> pl.DataFrame:
    """Map unique indications to EFO IDs via OnToma, with NER fallback."""
    unique = (
        df.select(pl.col("indication").alias("query_label"))
        .unique()
        .drop_nulls()
    )
    if unique.height == 0:
        return df.with_columns(
            pl.lit([], dtype=pl.List(pl.String)).alias("diseaseId")
        )

    query = unique.with_columns(pl.lit("DS").alias("entity_type"))
    query_spark = _convert_to_spark(query, spark).repartition(50, "entity_type")

    lut = OpenTargetsDisease.as_label_lut(disease_index)
    ontoma = OnToma(spark=spark, entity_lut_list=[lut])
    results = ontoma.map_entities(
        df=query_spark,
        result_col_name="mapped_ids",
        entity_col_name="query_label",
        entity_kind="label",
        type_col=f.col("entity_type"),
    )

    mapping_pl = pl.from_pandas(
        results
        .filter(f.col("mapped_ids").isNotNull() & (f.size("mapped_ids") > 0))
        .select("query_label", "mapped_ids")
        .toPandas()
    ).rename({"mapped_ids": "diseaseId"})

    dict_covered = mapping_pl.height
    total = unique.height
    logger.info(
        f"disease dict mapping: {dict_covered}/{total} "
        f"({dict_covered/total*100:.1f}%)"
    )

    # ── NER fallback for unmapped indications ──
    if ner_extract_disease:
        mapped_labels = mapping_pl.select("query_label").unique()
        unmapped = unique.join(mapped_labels, on="query_label", how="anti")
        unmapped_count = unmapped.height
        if unmapped_count > 0:
            logger.info(f"disease NER fallback: {unmapped_count} unmapped labels")
            ner_mapping = _ner_fallback_disease(unmapped, spark, lut)
            if ner_mapping is not None:
                mapping_pl = pl.concat([
                    mapping_pl,
                    ner_mapping.rename({"ner_mapped_ids": "diseaseId"}),
                ])

        covered = mapping_pl.height
        logger.info(
            f"disease mapping (dict+ner): {covered}/{total} "
            f"({covered/total*100:.1f}%)"
        )

    result = df.join(
        mapping_pl, left_on="indication", right_on="query_label", how="left"
    )
    return result.with_columns(
        pl.col("diseaseId").fill_null(pl.lit([], dtype=pl.List(pl.String)))
    )


# ── Todo 6: Greedy drug mapping ────────────────────────────────────────


def map_drugs(
    df: pl.DataFrame, spark: SparkSession, drug_index: DataFrame
) -> pl.DataFrame:
    """Greedy drug mapping via asset_name + synonyms, grouped as list, NER fallback."""
    df = df.with_row_index("__row_id")

    expanded = df.with_columns(
        pl.when(pl.col("synonyms").is_not_null())
        .then(pl.concat_list([pl.col("asset_name"), pl.col("synonyms")]))
        .otherwise(pl.concat_list([pl.col("asset_name"), pl.lit([], dtype=pl.List(pl.String))]))
        .alias("__all_names")
    ).explode("__all_names").select(
        "__row_id", pl.col("__all_names").alias("__drug_name")
    )

    unique_names = expanded.select("__drug_name").unique().drop_nulls()
    logger.info(f"drug mapping: {unique_names.height} unique drug names")

    if unique_names.height == 0:
        return df.with_columns(
            pl.lit([], dtype=pl.List(pl.String)).alias("drugId")
        ).drop("__row_id")

    query = unique_names.with_columns(pl.lit("CD").alias("entity_type"))
    query_spark = _convert_to_spark(query, spark).repartition(50, "entity_type")

    lut = OpenTargetsDrug.as_label_lut(drug_index)
    ontoma = OnToma(spark=spark, entity_lut_list=[lut])
    mapping_results = ontoma.map_entities(
        df=query_spark,
        result_col_name="mapped_ids",
        entity_col_name="__drug_name",
        entity_kind="label",
        type_col=f.col("entity_type"),
    )

    mapping_pl = pl.from_pandas(
        mapping_results
        .filter(f.col("mapped_ids").isNotNull() & (f.size("mapped_ids") > 0))
        .select("__drug_name", "mapped_ids")
        .toPandas()
    )

    dict_mapped_count = mapping_pl.height

    # ── NER fallback for unmapped drug names ──
    mapped_names = mapping_pl.select("__drug_name").unique()
    unmapped_names = unique_names.join(mapped_names, on="__drug_name", how="anti")
    unmapped_count = unmapped_names.height

    if unmapped_count > 0:
        logger.info(f"ner fallback: {unmapped_count} unmapped drug names")
        ner_mapping = _ner_fallback(unmapped_names, spark, lut)
        if ner_mapping is not None:
            mapping_pl = pl.concat(
                [mapping_pl, ner_mapping.rename({"ner_mapped_ids": "mapped_ids"})]
            )

    logger.info(
        f"drug mapping (dict: {dict_mapped_count} + ner: "
        f"{mapping_pl.height - dict_mapped_count} = {mapping_pl.height} names)"
    )

    mapped = expanded.join(mapping_pl, on="__drug_name", how="left")
    grouped = (
        mapped.filter(pl.col("mapped_ids").is_not_null())
        .explode("mapped_ids")
        .group_by("__row_id")
        .agg(pl.col("mapped_ids").unique().alias("drugId"))
    )

    result = df.join(grouped, on="__row_id", how="left").with_columns(
        pl.col("drugId").fill_null(pl.lit([], dtype=pl.List(pl.String)))
    )

    return result.drop("__row_id")


def _ner_fallback(
    unmapped: pl.DataFrame, spark: SparkSession, drug_lut
) -> pl.DataFrame | None:
    """NER fallback for drug names OnToma dictionary couldn't map."""
    labels = unmapped.select("__drug_name").unique()
    if labels.height == 0:
        return None

    ner_extracted_raw = None
    if os.path.exists(NER_DRUG_CACHE_PATH):
        try:
            cached = spark.read.parquet(NER_DRUG_CACHE_PATH)
            cached_labels = cached.select("__drug_name").distinct()
            labels = labels.join(cached_labels, on="__drug_name", how="left_anti")
            if cached.count() > 0:
                ner_extracted_raw = cached
                logger.info(f"ner cache loaded: {NER_DRUG_CACHE_PATH}")
        except Exception:
            logger.info("ner cache read failed, will recompute")

    new_count = labels.height
    if new_count > 0:
        logger.info(f"running NER on {new_count} new labels")
        ner_input = _convert_to_spark(
            labels.with_columns(
                pl.col("__drug_name").alias("query_label")
            ).select("query_label"),
            spark,
        )
        new_results = extract_drug_entities(
            spark=spark,
            df=ner_input,
            input_col="query_label",
            output_col="extracted_drugs",
            use_regex=True,
            use_biobert=True,
            use_drugtemist=True,
            batch_size=NER_BATCH_SIZE,
        )
        if ner_extracted_raw is not None:
            ner_extracted_raw = ner_extracted_raw.union(new_results)
        else:
            ner_extracted_raw = new_results

        os.makedirs(os.path.dirname(NER_DRUG_CACHE_PATH), exist_ok=True)
        ner_extracted_raw.toPandas().to_parquet(NER_DRUG_CACHE_PATH)
        logger.info(f"ner cache updated: {NER_DRUG_CACHE_PATH}")

    if ner_extracted_raw is None or ner_extracted_raw.count() == 0:
        return None

    ner_extracted = ner_extracted_raw.filter(f.size("extracted_drugs") > 0).select(
        f.col("query_label").alias("__drug_name"),
        f.explode("extracted_drugs").alias("clean_label"),
    )

    ontoma_clean = OnToma(spark=spark, entity_lut_list=[drug_lut])
    ner_mapped = ontoma_clean.map_entities(
        df=ner_extracted,
        result_col_name="mapped_ids",
        entity_col_name="clean_label",
        entity_kind="label",
        type_col=f.lit("CD"),
    )

    aggregated = pl.from_pandas(
        ner_mapped.filter(
            f.col("mapped_ids").isNotNull() & (f.size("mapped_ids") > 0)
        )
        .groupBy("__drug_name")
        .agg(
            f.array_distinct(f.flatten(f.collect_list("mapped_ids"))).alias(
                "ner_mapped_ids"
            )
        )
        .toPandas()
    )

    recovered = aggregated.height
    logger.info(f"ner recovered {recovered} drug names")
    return aggregated if recovered > 0 else None


def _ner_fallback_disease(
    unmapped: pl.DataFrame, spark: SparkSession, disease_lut
) -> pl.DataFrame | None:
    """NER fallback for indication labels OnToma dictionary couldn't map."""
    labels = unmapped.select("query_label").unique()
    if labels.height == 0:
        return None

    ner_extracted_raw = None
    if os.path.exists(NER_DISEASE_CACHE_PATH):
        try:
            cached = spark.read.parquet(NER_DISEASE_CACHE_PATH)
            cached_labels = cached.select("query_label").distinct()
            labels = labels.join(cached_labels, on="query_label", how="left_anti")
            if cached.count() > 0:
                ner_extracted_raw = cached
                logger.info(f"disease ner cache loaded: {NER_DISEASE_CACHE_PATH}")
        except Exception:
            logger.info("disease ner cache read failed, will recompute")

    new_count = labels.height
    if new_count > 0:
        logger.info(f"running disease NER on {new_count} new labels")
        ner_input = _convert_to_spark(
            labels.with_columns(
                pl.col("query_label").alias("query_label")
            ).select("query_label"),
            spark,
        )
        new_results = extract_disease_entities(
            spark=spark,
            df=ner_input,
            input_col="query_label",
            output_col="extracted_diseases",
        )
        if ner_extracted_raw is not None:
            ner_extracted_raw = ner_extracted_raw.union(new_results)
        else:
            ner_extracted_raw = new_results

        os.makedirs(os.path.dirname(NER_DISEASE_CACHE_PATH), exist_ok=True)
        ner_extracted_raw.toPandas().to_parquet(NER_DISEASE_CACHE_PATH)
        logger.info(f"disease ner cache updated: {NER_DISEASE_CACHE_PATH}")

    if ner_extracted_raw is None or ner_extracted_raw.count() == 0:
        return None

    ner_extracted = ner_extracted_raw.filter(
        f.size("extracted_diseases") > 0
    ).select(
        f.col("query_label"),
        f.explode("extracted_diseases").alias("clean_label"),
    )

    ontoma_clean = OnToma(spark=spark, entity_lut_list=[disease_lut])
    ner_mapped = ontoma_clean.map_entities(
        df=ner_extracted,
        result_col_name="mapped_ids",
        entity_col_name="clean_label",
        entity_kind="label",
        type_col=f.lit("DS"),
    )

    aggregated = pl.from_pandas(
        ner_mapped.filter(
            f.col("mapped_ids").isNotNull() & (f.size("mapped_ids") > 0)
        )
        .groupBy("query_label")
        .agg(
            f.array_distinct(f.flatten(f.collect_list("mapped_ids"))).alias(
                "ner_mapped_ids"
            )
        )
        .toPandas()
    )

    recovered = aggregated.height
    logger.info(f"disease ner recovered {recovered} indication labels")
    return aggregated if recovered > 0 else None


# ── Todo 7: Main entry point ──────────────────────────────────────────


def main():
    logger.info("=== Pharma Portfolio -> OT Ingestion ===")

    logger.info("[1/5] loading all pipelines...")
    df = load_all_pipelines()
    initial_rows = len(df)

    logger.info("[2/5] creating spark session...")
    spark = create_spark()

    try:
        logger.info("[3/5] loading indexes...")
        disease_index = load_disease_index(spark)
        drug_index = load_drug_index(spark)

        logger.info("[4/5] mapping diseases...")
        df = map_diseases(df, spark, disease_index)

        logger.info("[5/5] mapping drugs (greedy)...")
        df = map_drugs(df, spark, drug_index)

        logger.info("[6/5] writing output...")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        output_path = str(DATA_DIR / "pharma_portfolio_enriched.parquet")
        df.write_parquet(output_path)

        final_rows = len(df)
        drug_covered = df.filter(pl.col("drugId").list.len() > 0).height
        disease_covered = df.filter(pl.col("diseaseId").list.len() > 0).height
        drug_pct = drug_covered / final_rows * 100
        disease_pct = disease_covered / final_rows * 100

        logger.info(f"rows: {final_rows} (initial: {initial_rows})")
        logger.info(f"drug coverage: {drug_covered}/{final_rows} ({drug_pct:.1f}%)")
        logger.info(f"disease coverage: {disease_covered}/{final_rows} ({disease_pct:.1f}%)")
        logger.info(f"output: {output_path}")

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
