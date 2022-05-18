from typing import Optional, Union

import great_expectations.exceptions as ge_exceptions
from great_expectations.core.id_dict import BatchSpec
from great_expectations.execution_engine.split_and_sample.data_sampler import (
    DataSampler,
)
from great_expectations.execution_engine.sqlalchemy_dialect import GESqlDialect

try:
    import sqlalchemy as sa
except ImportError:
    sa = None

try:
    from sqlalchemy.engine import Dialect
    from sqlalchemy.sql import Selectable
    from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList
except ImportError:
    Selectable = None
    BinaryExpression = None
    BooleanClauseList = None
    Dialect = None


class SqlAlchemyDataSampler(DataSampler):
    """Sampling methods for data stores with SQL interfaces."""

    def sample_using_limit(
        self,
        execution_engine: "SqlAlchemyExecutionEngine",  # noqa: F821
        batch_spec: BatchSpec,
        where_clause: Optional[Selectable] = None,
    ) -> Union[str, BinaryExpression, BooleanClauseList]:
        """Sample using a limit with configuration provided via the batch_spec.

        Note: where_clause needs to be included at this stage since SqlAlchemy's semantics
        for LIMIT are different than normal WHERE clauses.

        Also this requires an engine to find the dialect since certain databases require
        different handling.

        Args:
            execution_engine: Engine used to connect to the database.
            batch_spec: Batch specification describing the batch of interest.
            where_clause: Optional clause used in WHERE clause. Typically generated by a splitter.

        Returns:
            A query as a string or sqlalchemy object.
        """

        # Split clause should be permissive of all values if not supplied.
        if not where_clause:
            where_clause = True

        table_name: str = batch_spec["table_name"]

        # SQLalchemy's semantics for LIMIT are different than normal WHERE clauses,
        # so the business logic for building the query needs to be different.
        dialect_name: str = execution_engine.dialect_name
        if dialect_name == GESqlDialect.ORACLE.value:
            # TODO: AJB 20220429 WARNING THIS oracle dialect METHOD IS NOT COVERED BY TESTS
            # limit doesn't compile properly for oracle so we will append rownum to query string later
            raw_query: Selectable = (
                sa.select("*")
                .select_from(
                    sa.table(table_name, schema=batch_spec.get("schema_name", None))
                )
                .where(where_clause)
            )
            query: str = str(
                raw_query.compile(
                    dialect=execution_engine.dialect,
                    compile_kwargs={"literal_binds": True},
                )
            )
            query += "\nAND ROWNUM <= %d" % batch_spec["sampling_kwargs"]["n"]
            return query
        elif dialect_name == GESqlDialect.MSSQL.value:
            # TODO: AJB 20220429 WARNING THIS mssql dialect METHOD IS NOT COVERED BY TESTS
            # Note that this code path exists because the limit parameter is not getting rendered
            # successfully in the resulting mssql query.
            selectable_query: Selectable = (
                sa.select("*")
                .select_from(
                    sa.table(table_name, schema=batch_spec.get("schema_name", None))
                )
                .where(where_clause)
                .limit(batch_spec["sampling_kwargs"]["n"])
            )
            string_of_query: str = str(
                selectable_query.compile(
                    dialect=execution_engine.dialect,
                    compile_kwargs={"literal_binds": True},
                )
            )
            n: Union[str, int] = batch_spec["sampling_kwargs"]["n"]
            self._validate_mssql_limit_param(n)
            # This string replacement is here because the limit parameter is not substituted during query.compile()
            string_of_query = string_of_query.replace("?", str(n))
            return string_of_query
        else:
            return (
                sa.select("*")
                .select_from(
                    sa.table(table_name, schema=batch_spec.get("schema_name", None))
                )
                .where(where_clause)
                .limit(batch_spec["sampling_kwargs"]["n"])
            )

    def _validate_mssql_limit_param(self, n: Union[str, int]) -> None:
        """Validate that the mssql limit param is passed as an int or a string representation of an int.

        Args:
            n: mssql limit parameter.

        Returns:
            None
        """
        if not isinstance(n, (str, int)):
            raise ge_exceptions.InvalidConfigError(
                "Please specify your sampling kwargs 'n' parameter as a string or int."
            )
        if isinstance(n, str) and not n.isdigit():
            raise ge_exceptions.InvalidConfigError(
                "If specifying your sampling kwargs 'n' parameter as a string please ensure it is "
                "parseable as an integer."
            )

    def sample_using_random(
        self,
        execution_engine: "SqlAlchemyExecutionEngine",  # noqa: F821
        batch_spec: BatchSpec,
        where_clause: Optional[Selectable] = None,
    ) -> Selectable:
        """Sample using random data with configuration provided via the batch_spec.

        Note: where_clause needs to be included at this stage since we use the where clause
        to determine the total number of rows to use in determining the rows returned in the
        sample fraction.

        Args:
            execution_engine: Engine used to connect to the database.
            batch_spec: Batch specification describing the batch of interest.
            where_clause: Optional clause used in WHERE clause. Typically generated by a splitter.

        Returns:
            Sqlalchemy selectable.
        """

        # TODO: AJB 20220429 WARNING THIS METHOD IS NOT COVERED BY TESTS

        table_name: str = batch_spec["table_name"]

        num_rows: int = execution_engine.engine.execute(
            sa.select([sa.func.count()])
            .select_from(
                sa.table(table_name, schema=batch_spec.get("schema_name", None))
            )
            .where(where_clause)
        ).scalar()
        p: float = batch_spec["sampling_kwargs"]["p"] or 1.0
        sample_size: int = round(p * num_rows)
        return (
            sa.select("*")
            .select_from(
                sa.table(table_name, schema=batch_spec.get("schema_name", None))
            )
            .where(where_clause)
            .order_by(sa.func.random())
            .limit(sample_size)
        )

    def sample_using_mod(
        self,
        column_name: str,
        mod: int,
        value: int,
    ) -> bool:
        """Take the mod of named column, and only keep rows that match the given value"""
        return sa.column(column_name) % mod == value

    def sample_using_a_list(
        self,
        column_name: str,
        value_list: list,
    ) -> bool:
        """Match the values in the named column against value_list, and only keep the matches"""
        return sa.column(column_name).in_(value_list)

    def sample_using_md5(
        self,
        column_name: str,
        hash_digits: int = 1,
        hash_value: str = "f",
    ) -> bool:
        """Hash the values in the named column, and split on that"""
        return (
            sa.func.right(
                sa.func.md5(sa.cast(sa.column(column_name), sa.Text)), hash_digits
            )
            == hash_value
        )
