import os
from typing import Any, Dict, List

import nbconvert
import nbformat
import pytest
from freezegun import freeze_time

from great_expectations import DataContext
from great_expectations.core import ExpectationConfiguration, ExpectationSuite
from great_expectations.rule_based_profiler.config import RuleBasedProfilerConfig
from great_expectations.rule_based_profiler.data_assistant import (
    DataAssistant,
    VolumeDataAssistant,
)
from great_expectations.rule_based_profiler.types import Domain
from great_expectations.rule_based_profiler.types.data_assistant_result import (
    DataAssistantResult,
)
from great_expectations.util import deep_filter_properties_iterable
from great_expectations.validator.validator import Validator
from tests.render.test_util import load_notebook_from_path
from tests.rule_based_profiler.parameter_builder.conftest import RANDOM_SEED
from tests.test_utils import (
    get_or_create_expectation_suite,
    get_validator_with_expectation_suite,
    set_bootstrap_random_seed_variable,
)


def run_volume_data_assistant_result_jupyter_notebook_with_new_cell(
    context: DataContext, new_cell: str
):
    """
    To set this test up we:
    - create a suite
    - write code (as a string) for creating a VolumeDataAssistantResult
    - add a new cell to the notebook that was passed to this method
    - write both cells to ipynb file

    We then:
    - load the notebook back from disk
    - execute the notebook (Note: this will raise various errors like
      CellExecutionError if any cell in the notebook fails)
    """

    root_dir: str = context.root_directory
    expectation_suite_name: str = "test_suite"
    context.create_expectation_suite(expectation_suite_name)
    notebook_path: str = os.path.join(root_dir, f"run_volume_data_assistant.ipynb")
    notebook_code: str = """
    from typing import Optional, Union

    import uuid

    import great_expectations as ge
    from great_expectations.data_context import BaseDataContext
    from great_expectations.core.batch import BatchRequestBase, materialize_batch_request
    from great_expectations.core import ExpectationSuite
    from great_expectations.validator.validator import Validator
    from great_expectations.rule_based_profiler.data_assistant import (
        DataAssistant,
        VolumeDataAssistant,
    )
    from great_expectations.rule_based_profiler.types.data_assistant_result import DataAssistantResult
    import great_expectations.exceptions as ge_exceptions
    """
    notebook_code += """
    def get_validator_with_expectation_suite(
        batch_request: Union[BatchRequestBase, dict],
        data_context: BaseDataContext,
        expectation_suite: Optional[ExpectationSuite] = None,
        expectation_suite_name: Optional[str] = None,
        component_name: Optional[str] = None,
    ) -> Validator:
        expectation_suite: ExpectationSuite

        generate_temp_expectation_suite_name: bool
        create_expectation_suite: bool

        if expectation_suite is not None and expectation_suite_name is not None:
            if expectation_suite.expectation_suite_name != expectation_suite_name:
                raise ValueError(
                    'Mutually inconsistent "expectation_suite" and "expectation_suite_name" were specified.'
                )
            generate_temp_expectation_suite_name = False
            create_expectation_suite = False
        elif expectation_suite is None and expectation_suite_name is not None:
            generate_temp_expectation_suite_name = False
            create_expectation_suite = True
        elif expectation_suite is not None and expectation_suite_name is None:
            generate_temp_expectation_suite_name = False
            create_expectation_suite = False
        else:
            generate_temp_expectation_suite_name = True
            create_expectation_suite = True

        if generate_temp_expectation_suite_name:
            if not component_name:
                component_name = "test"

            expectation_suite_name = f"tmp.{component_name}.suite_{str(uuid.uuid4())[:8]}"

        if create_expectation_suite:
            try:
                # noinspection PyUnusedLocal
                expectation_suite = data_context.get_expectation_suite(
                    expectation_suite_name=expectation_suite_name
                )
            except ge_exceptions.DataContextError:
                expectation_suite = data_context.create_expectation_suite(
                    expectation_suite_name=expectation_suite_name
                )
                print(f'Created ExpectationSuite "{expectation_suite.expectation_suite_name}".')

        batch_request = materialize_batch_request(batch_request=batch_request)
        validator: Validator = data_context.get_validator(
            batch_request=batch_request,
            expectation_suite_name=expectation_suite_name,
        )

        return validator
    """
    notebook_code += """
    context = ge.get_context()

    batch_request: dict = {
        "datasource_name": "taxi_pandas",
        "data_connector_name": "monthly",
        "data_asset_name": "my_reports",
    }

    validator: Validator = get_validator_with_expectation_suite(
        batch_request=batch_request,
        data_context=context,
        expectation_suite_name=None,
        expectation_suite=None,
        component_name="volume_data_assistant",
    )

    data_assistant: DataAssistant = VolumeDataAssistant(
        name="test_volume_data_assistant",
        validator=validator,
    )

    expectation_suite_name: str = "test_suite"
    data_assistant_result: DataAssistantResult = data_assistant.run(
        expectation_suite_name=expectation_suite_name,
    )
    """

    nb = nbformat.v4.new_notebook()
    nb["cells"] = []
    nb["cells"].append(nbformat.v4.new_code_cell(notebook_code))
    nb["cells"].append(nbformat.v4.new_code_cell(new_cell))

    # Write notebook to path and load it as NotebookNode
    with open(notebook_path, "w") as f:
        nbformat.write(nb, f)

    nb: nbformat.notebooknode.NotebookNode = load_notebook_from_path(
        notebook_path=notebook_path
    )

    # Run notebook
    ep: nbconvert.preprocessors.ExecutePreprocessor = (
        nbconvert.preprocessors.ExecutePreprocessor(timeout=60, kernel_name="python3")
    )
    ep.preprocess(nb, {"metadata": {"path": root_dir}})


@freeze_time("09/26/2019 13:42:41")
def test_get_metrics_and_expectations(
    quentin_columnar_table_multi_batch_data_context,
):
    context: DataContext = quentin_columnar_table_multi_batch_data_context

    batch_request: dict = {
        "datasource_name": "taxi_pandas",
        "data_connector_name": "monthly",
        "data_asset_name": "my_reports",
    }

    validator: Validator = get_validator_with_expectation_suite(
        batch_request=batch_request,
        data_context=context,
        expectation_suite_name=None,
        expectation_suite=None,
        component_name="volume_data_assistant",
    )
    assert len(validator.batches) == 36

    expected_metrics_by_domain: Dict[Domain, Dict[str, Any]] = {
        Domain(domain_type="table",): {
            "$parameter.table_row_count": {
                "value": [
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                    10000,
                ],
                "attributed_value": {
                    "0327cfb13205ec8512e1c28e438ab43b": [10000],
                    "08085632aff9ce4cebbb8023049e1aec": [10000],
                    "0808e185a52825d22356de2fe00a8f5f": [10000],
                    "33d910f95326c0c7dfe7536d1cfeba51": [10000],
                    "3692b23382fd4734215465251290c65b": [10000],
                    "44c1b1947c9049e7db62c5320dde4c63": [10000],
                    "47157bdaf05a7992473cd699cabaef74": [10000],
                    "562969eaef9c843cb4531aecbc13bbcb": [10000],
                    "569a4a80bf434c888593c651dbf2f157": [10000],
                    "57c04d62ada3a102248b48f34c755159": [10000],
                    "58ce3b40d384eacd9bad7d916eb8f705": [10000],
                    "61e4931d87cb627df2a19b8bc5819b7b": [10000],
                    "6c7e43619fe5e6963e8159cc84a28321": [10000],
                    "73612fdabd337d5a8279acc30ce22d00": [10000],
                    "7b3ce20a8e8cf3097bb9df270a7ae63a": [10000],
                    "816b147dcf3305839f723a131b9ad6af": [10000],
                    "84000630d1b69a0fe870c94fb26a32bc": [10000],
                    "8ce0d477f610ea18e2ea4fbbb46de857": [10000],
                    "90bb41c1fbd7c71c05dbc8695320af71": [10000],
                    "940576153c66af14a949fd19aedd5f5b": [10000],
                    "976b121b46db6967854b9c1a6628396b": [10000],
                    "9e58d3c72c7006b6f5800b623fbc9818": [10000],
                    "ab05b4fb82e37c8cf5b1ac40d0a37fe9": [10000],
                    "ad2ad2a70c3e0bf94ddef3f893e92291": [10000],
                    "b20800a7faafd2808d6c888577a2ba1d": [10000],
                    "bb54e4fa3906387218be10cff631a7c2": [10000],
                    "bb81456ec79522bf02f34b02762f95e0": [10000],
                    "c4fe9afce1cf3e83eb8518a9f5abc754": [10000],
                    "c92d0679f769ac83fef2bb5eaac5d12a": [10000],
                    "ce5f02ac408b7b5c500050190f549736": [10000],
                    "e20c38f98b9830a40b851939ca7189d4": [10000],
                    "eff8910cddcdff62e4741243099240d5": [10000],
                    "f2e4d3da6556638b55df8ce509b094c2": [10000],
                    "f67d274202366f6b976414c950ca14bd": [10000],
                    "f6c389dcef63c1f214c30f66b66945c0": [10000],
                    "ff5a6cc031dd2c98b8bccd4766af38c1": [10000],
                },
                "details": {
                    "metric_configuration": {
                        "metric_name": "table.row_count",
                        "domain_kwargs": {},
                        "metric_value_kwargs": None,
                        "metric_dependencies": None,
                    },
                    "num_batches": 36,
                },
            },
        },
        Domain(domain_type="column", domain_kwargs={"column": "vendor_id",}): {
            "$parameter.column_distinct_values.count": {
                "value": [
                    3,
                    3,
                    3,
                    2,
                    2,
                    3,
                    3,
                    2,
                    2,
                    2,
                    3,
                    2,
                    3,
                    2,
                    2,
                    2,
                    2,
                    2,
                    3,
                    2,
                    3,
                    3,
                    2,
                    2,
                    2,
                    3,
                    3,
                    2,
                    2,
                    3,
                    2,
                    2,
                    3,
                    2,
                    2,
                    2,
                ],
                "attributed_value": {
                    "0327cfb13205ec8512e1c28e438ab43b": [3],
                    "08085632aff9ce4cebbb8023049e1aec": [3],
                    "0808e185a52825d22356de2fe00a8f5f": [3],
                    "33d910f95326c0c7dfe7536d1cfeba51": [2],
                    "3692b23382fd4734215465251290c65b": [2],
                    "44c1b1947c9049e7db62c5320dde4c63": [3],
                    "47157bdaf05a7992473cd699cabaef74": [3],
                    "562969eaef9c843cb4531aecbc13bbcb": [2],
                    "569a4a80bf434c888593c651dbf2f157": [2],
                    "57c04d62ada3a102248b48f34c755159": [2],
                    "58ce3b40d384eacd9bad7d916eb8f705": [3],
                    "61e4931d87cb627df2a19b8bc5819b7b": [2],
                    "6c7e43619fe5e6963e8159cc84a28321": [3],
                    "73612fdabd337d5a8279acc30ce22d00": [2],
                    "7b3ce20a8e8cf3097bb9df270a7ae63a": [2],
                    "816b147dcf3305839f723a131b9ad6af": [2],
                    "84000630d1b69a0fe870c94fb26a32bc": [2],
                    "8ce0d477f610ea18e2ea4fbbb46de857": [2],
                    "90bb41c1fbd7c71c05dbc8695320af71": [3],
                    "940576153c66af14a949fd19aedd5f5b": [2],
                    "976b121b46db6967854b9c1a6628396b": [3],
                    "9e58d3c72c7006b6f5800b623fbc9818": [3],
                    "ab05b4fb82e37c8cf5b1ac40d0a37fe9": [2],
                    "ad2ad2a70c3e0bf94ddef3f893e92291": [2],
                    "b20800a7faafd2808d6c888577a2ba1d": [2],
                    "bb54e4fa3906387218be10cff631a7c2": [3],
                    "bb81456ec79522bf02f34b02762f95e0": [3],
                    "c4fe9afce1cf3e83eb8518a9f5abc754": [2],
                    "c92d0679f769ac83fef2bb5eaac5d12a": [2],
                    "ce5f02ac408b7b5c500050190f549736": [3],
                    "e20c38f98b9830a40b851939ca7189d4": [2],
                    "eff8910cddcdff62e4741243099240d5": [2],
                    "f2e4d3da6556638b55df8ce509b094c2": [3],
                    "f67d274202366f6b976414c950ca14bd": [2],
                    "f6c389dcef63c1f214c30f66b66945c0": [2],
                    "ff5a6cc031dd2c98b8bccd4766af38c1": [2],
                },
                "details": {
                    "metric_configuration": {
                        "metric_name": "column.distinct_values.count",
                        "domain_kwargs": {"column": "vendor_id"},
                        "metric_value_kwargs": None,
                        "metric_dependencies": None,
                    },
                    "num_batches": 36,
                },
            }
        },
        Domain(domain_type="column", domain_kwargs={"column": "pickup_datetime",}): {
            "$parameter.column_distinct_values.count": {
                "value": [
                    9973,
                    9968,
                    9977,
                    9981,
                    9976,
                    9974,
                    9974,
                    9965,
                    9974,
                    9970,
                    9977,
                    9973,
                    9984,
                    9955,
                    9945,
                    9977,
                    9969,
                    9953,
                    9976,
                    9955,
                    9977,
                    9970,
                    9962,
                    9941,
                    9976,
                    9972,
                    9975,
                    9976,
                    9979,
                    9977,
                    9980,
                    9982,
                    9983,
                    9981,
                    9979,
                    9973,
                ],
                "attributed_value": {
                    "0327cfb13205ec8512e1c28e438ab43b": [9973],
                    "08085632aff9ce4cebbb8023049e1aec": [9968],
                    "0808e185a52825d22356de2fe00a8f5f": [9977],
                    "33d910f95326c0c7dfe7536d1cfeba51": [9981],
                    "3692b23382fd4734215465251290c65b": [9976],
                    "44c1b1947c9049e7db62c5320dde4c63": [9974],
                    "47157bdaf05a7992473cd699cabaef74": [9974],
                    "562969eaef9c843cb4531aecbc13bbcb": [9965],
                    "569a4a80bf434c888593c651dbf2f157": [9974],
                    "57c04d62ada3a102248b48f34c755159": [9970],
                    "58ce3b40d384eacd9bad7d916eb8f705": [9977],
                    "61e4931d87cb627df2a19b8bc5819b7b": [9973],
                    "6c7e43619fe5e6963e8159cc84a28321": [9984],
                    "73612fdabd337d5a8279acc30ce22d00": [9955],
                    "7b3ce20a8e8cf3097bb9df270a7ae63a": [9945],
                    "816b147dcf3305839f723a131b9ad6af": [9977],
                    "84000630d1b69a0fe870c94fb26a32bc": [9969],
                    "8ce0d477f610ea18e2ea4fbbb46de857": [9953],
                    "90bb41c1fbd7c71c05dbc8695320af71": [9976],
                    "940576153c66af14a949fd19aedd5f5b": [9955],
                    "976b121b46db6967854b9c1a6628396b": [9977],
                    "9e58d3c72c7006b6f5800b623fbc9818": [9970],
                    "ab05b4fb82e37c8cf5b1ac40d0a37fe9": [9962],
                    "ad2ad2a70c3e0bf94ddef3f893e92291": [9941],
                    "b20800a7faafd2808d6c888577a2ba1d": [9976],
                    "bb54e4fa3906387218be10cff631a7c2": [9972],
                    "bb81456ec79522bf02f34b02762f95e0": [9975],
                    "c4fe9afce1cf3e83eb8518a9f5abc754": [9976],
                    "c92d0679f769ac83fef2bb5eaac5d12a": [9979],
                    "ce5f02ac408b7b5c500050190f549736": [9977],
                    "e20c38f98b9830a40b851939ca7189d4": [9980],
                    "eff8910cddcdff62e4741243099240d5": [9982],
                    "f2e4d3da6556638b55df8ce509b094c2": [9983],
                    "f67d274202366f6b976414c950ca14bd": [9981],
                    "f6c389dcef63c1f214c30f66b66945c0": [9979],
                    "ff5a6cc031dd2c98b8bccd4766af38c1": [9973],
                },
                "details": {
                    "metric_configuration": {
                        "metric_name": "column.distinct_values.count",
                        "domain_kwargs": {"column": "pickup_datetime"},
                        "metric_value_kwargs": None,
                        "metric_dependencies": None,
                    },
                    "num_batches": 36,
                },
            }
        },
        Domain(domain_type="column", domain_kwargs={"column": "dropoff_datetime",}): {
            "$parameter.column_distinct_values.count": {
                "value": [
                    9972,
                    9976,
                    9967,
                    9984,
                    9975,
                    9977,
                    9971,
                    9977,
                    9972,
                    9967,
                    9972,
                    9977,
                    9976,
                    9964,
                    9968,
                    9976,
                    9971,
                    9965,
                    9973,
                    9978,
                    9986,
                    9982,
                    9970,
                    9939,
                    9974,
                    9975,
                    9978,
                    9984,
                    9979,
                    9982,
                    9977,
                    9975,
                    9985,
                    9973,
                    9979,
                    9966,
                ],
                "attributed_value": {
                    "0327cfb13205ec8512e1c28e438ab43b": [9972],
                    "08085632aff9ce4cebbb8023049e1aec": [9976],
                    "0808e185a52825d22356de2fe00a8f5f": [9967],
                    "33d910f95326c0c7dfe7536d1cfeba51": [9984],
                    "3692b23382fd4734215465251290c65b": [9975],
                    "44c1b1947c9049e7db62c5320dde4c63": [9977],
                    "47157bdaf05a7992473cd699cabaef74": [9971],
                    "562969eaef9c843cb4531aecbc13bbcb": [9977],
                    "569a4a80bf434c888593c651dbf2f157": [9972],
                    "57c04d62ada3a102248b48f34c755159": [9967],
                    "58ce3b40d384eacd9bad7d916eb8f705": [9972],
                    "61e4931d87cb627df2a19b8bc5819b7b": [9977],
                    "6c7e43619fe5e6963e8159cc84a28321": [9976],
                    "73612fdabd337d5a8279acc30ce22d00": [9964],
                    "7b3ce20a8e8cf3097bb9df270a7ae63a": [9968],
                    "816b147dcf3305839f723a131b9ad6af": [9976],
                    "84000630d1b69a0fe870c94fb26a32bc": [9971],
                    "8ce0d477f610ea18e2ea4fbbb46de857": [9965],
                    "90bb41c1fbd7c71c05dbc8695320af71": [9973],
                    "940576153c66af14a949fd19aedd5f5b": [9978],
                    "976b121b46db6967854b9c1a6628396b": [9986],
                    "9e58d3c72c7006b6f5800b623fbc9818": [9982],
                    "ab05b4fb82e37c8cf5b1ac40d0a37fe9": [9970],
                    "ad2ad2a70c3e0bf94ddef3f893e92291": [9939],
                    "b20800a7faafd2808d6c888577a2ba1d": [9974],
                    "bb54e4fa3906387218be10cff631a7c2": [9975],
                    "bb81456ec79522bf02f34b02762f95e0": [9978],
                    "c4fe9afce1cf3e83eb8518a9f5abc754": [9984],
                    "c92d0679f769ac83fef2bb5eaac5d12a": [9979],
                    "ce5f02ac408b7b5c500050190f549736": [9982],
                    "e20c38f98b9830a40b851939ca7189d4": [9977],
                    "eff8910cddcdff62e4741243099240d5": [9975],
                    "f2e4d3da6556638b55df8ce509b094c2": [9985],
                    "f67d274202366f6b976414c950ca14bd": [9973],
                    "f6c389dcef63c1f214c30f66b66945c0": [9979],
                    "ff5a6cc031dd2c98b8bccd4766af38c1": [9966],
                },
                "details": {
                    "metric_configuration": {
                        "metric_name": "column.distinct_values.count",
                        "domain_kwargs": {"column": "dropoff_datetime"},
                        "metric_value_kwargs": None,
                        "metric_dependencies": None,
                    },
                    "num_batches": 36,
                },
            }
        },
        Domain(domain_type="column", domain_kwargs={"column": "passenger_count",}): {
            "$parameter.column_distinct_values.count": {
                "value": [
                    6,
                    7,
                    7,
                    7,
                    8,
                    7,
                    7,
                    7,
                    7,
                    7,
                    8,
                    7,
                    7,
                    7,
                    7,
                    7,
                    7,
                    7,
                    7,
                    7,
                    7,
                    8,
                    7,
                    7,
                    7,
                    7,
                    7,
                    7,
                    7,
                    7,
                    7,
                    7,
                    8,
                    7,
                    7,
                    7,
                ],
                "attributed_value": {
                    "0327cfb13205ec8512e1c28e438ab43b": [6],
                    "08085632aff9ce4cebbb8023049e1aec": [7],
                    "0808e185a52825d22356de2fe00a8f5f": [7],
                    "33d910f95326c0c7dfe7536d1cfeba51": [7],
                    "3692b23382fd4734215465251290c65b": [8],
                    "44c1b1947c9049e7db62c5320dde4c63": [7],
                    "47157bdaf05a7992473cd699cabaef74": [7],
                    "562969eaef9c843cb4531aecbc13bbcb": [7],
                    "569a4a80bf434c888593c651dbf2f157": [7],
                    "57c04d62ada3a102248b48f34c755159": [7],
                    "58ce3b40d384eacd9bad7d916eb8f705": [8],
                    "61e4931d87cb627df2a19b8bc5819b7b": [7],
                    "6c7e43619fe5e6963e8159cc84a28321": [7],
                    "73612fdabd337d5a8279acc30ce22d00": [7],
                    "7b3ce20a8e8cf3097bb9df270a7ae63a": [7],
                    "816b147dcf3305839f723a131b9ad6af": [7],
                    "84000630d1b69a0fe870c94fb26a32bc": [7],
                    "8ce0d477f610ea18e2ea4fbbb46de857": [7],
                    "90bb41c1fbd7c71c05dbc8695320af71": [7],
                    "940576153c66af14a949fd19aedd5f5b": [7],
                    "976b121b46db6967854b9c1a6628396b": [7],
                    "9e58d3c72c7006b6f5800b623fbc9818": [8],
                    "ab05b4fb82e37c8cf5b1ac40d0a37fe9": [7],
                    "ad2ad2a70c3e0bf94ddef3f893e92291": [7],
                    "b20800a7faafd2808d6c888577a2ba1d": [7],
                    "bb54e4fa3906387218be10cff631a7c2": [7],
                    "bb81456ec79522bf02f34b02762f95e0": [7],
                    "c4fe9afce1cf3e83eb8518a9f5abc754": [7],
                    "c92d0679f769ac83fef2bb5eaac5d12a": [7],
                    "ce5f02ac408b7b5c500050190f549736": [7],
                    "e20c38f98b9830a40b851939ca7189d4": [7],
                    "eff8910cddcdff62e4741243099240d5": [7],
                    "f2e4d3da6556638b55df8ce509b094c2": [8],
                    "f67d274202366f6b976414c950ca14bd": [7],
                    "f6c389dcef63c1f214c30f66b66945c0": [7],
                    "ff5a6cc031dd2c98b8bccd4766af38c1": [7],
                },
                "details": {
                    "metric_configuration": {
                        "metric_name": "column.distinct_values.count",
                        "domain_kwargs": {"column": "passenger_count"},
                        "metric_value_kwargs": None,
                        "metric_dependencies": None,
                    },
                    "num_batches": 36,
                },
            }
        },
        Domain(domain_type="column", domain_kwargs={"column": "trip_distance",}): {
            "$parameter.column_distinct_values.count": {
                "value": [
                    1184,
                    1192,
                    1200,
                    1279,
                    1249,
                    1252,
                    1236,
                    1141,
                    1165,
                    1188,
                    1206,
                    1230,
                    1240,
                    1273,
                    1253,
                    1204,
                    1196,
                    1430,
                    1225,
                    1319,
                    1222,
                    1266,
                    1207,
                    1560,
                    1310,
                    1212,
                    1293,
                    1202,
                    1157,
                    1299,
                    1202,
                    1228,
                    1227,
                    1190,
                    1176,
                    1371,
                ],
                "attributed_value": {
                    "0327cfb13205ec8512e1c28e438ab43b": [1184],
                    "08085632aff9ce4cebbb8023049e1aec": [1192],
                    "0808e185a52825d22356de2fe00a8f5f": [1200],
                    "33d910f95326c0c7dfe7536d1cfeba51": [1279],
                    "3692b23382fd4734215465251290c65b": [1249],
                    "44c1b1947c9049e7db62c5320dde4c63": [1252],
                    "47157bdaf05a7992473cd699cabaef74": [1236],
                    "562969eaef9c843cb4531aecbc13bbcb": [1141],
                    "569a4a80bf434c888593c651dbf2f157": [1165],
                    "57c04d62ada3a102248b48f34c755159": [1188],
                    "58ce3b40d384eacd9bad7d916eb8f705": [1206],
                    "61e4931d87cb627df2a19b8bc5819b7b": [1230],
                    "6c7e43619fe5e6963e8159cc84a28321": [1240],
                    "73612fdabd337d5a8279acc30ce22d00": [1273],
                    "7b3ce20a8e8cf3097bb9df270a7ae63a": [1253],
                    "816b147dcf3305839f723a131b9ad6af": [1204],
                    "84000630d1b69a0fe870c94fb26a32bc": [1196],
                    "8ce0d477f610ea18e2ea4fbbb46de857": [1430],
                    "90bb41c1fbd7c71c05dbc8695320af71": [1225],
                    "940576153c66af14a949fd19aedd5f5b": [1319],
                    "976b121b46db6967854b9c1a6628396b": [1222],
                    "9e58d3c72c7006b6f5800b623fbc9818": [1266],
                    "ab05b4fb82e37c8cf5b1ac40d0a37fe9": [1207],
                    "ad2ad2a70c3e0bf94ddef3f893e92291": [1560],
                    "b20800a7faafd2808d6c888577a2ba1d": [1310],
                    "bb54e4fa3906387218be10cff631a7c2": [1212],
                    "bb81456ec79522bf02f34b02762f95e0": [1293],
                    "c4fe9afce1cf3e83eb8518a9f5abc754": [1202],
                    "c92d0679f769ac83fef2bb5eaac5d12a": [1157],
                    "ce5f02ac408b7b5c500050190f549736": [1299],
                    "e20c38f98b9830a40b851939ca7189d4": [1202],
                    "eff8910cddcdff62e4741243099240d5": [1228],
                    "f2e4d3da6556638b55df8ce509b094c2": [1227],
                    "f67d274202366f6b976414c950ca14bd": [1190],
                    "f6c389dcef63c1f214c30f66b66945c0": [1176],
                    "ff5a6cc031dd2c98b8bccd4766af38c1": [1371],
                },
                "details": {
                    "metric_configuration": {
                        "metric_name": "column.distinct_values.count",
                        "domain_kwargs": {"column": "trip_distance"},
                        "metric_value_kwargs": None,
                        "metric_dependencies": None,
                    },
                    "num_batches": 36,
                },
            }
        },
        Domain(domain_type="column", domain_kwargs={"column": "rate_code_id",}): {
            "$parameter.column_distinct_values.count": {
                "value": [
                    7,
                    6,
                    5,
                    5,
                    5,
                    6,
                    6,
                    5,
                    5,
                    6,
                    6,
                    5,
                    5,
                    6,
                    5,
                    5,
                    5,
                    6,
                    5,
                    5,
                    5,
                    6,
                    5,
                    6,
                    5,
                    6,
                    6,
                    5,
                    5,
                    5,
                    6,
                    5,
                    5,
                    6,
                    6,
                    6,
                ],
                "attributed_value": {
                    "0327cfb13205ec8512e1c28e438ab43b": [7],
                    "08085632aff9ce4cebbb8023049e1aec": [6],
                    "0808e185a52825d22356de2fe00a8f5f": [5],
                    "33d910f95326c0c7dfe7536d1cfeba51": [5],
                    "3692b23382fd4734215465251290c65b": [5],
                    "44c1b1947c9049e7db62c5320dde4c63": [6],
                    "47157bdaf05a7992473cd699cabaef74": [6],
                    "562969eaef9c843cb4531aecbc13bbcb": [5],
                    "569a4a80bf434c888593c651dbf2f157": [5],
                    "57c04d62ada3a102248b48f34c755159": [6],
                    "58ce3b40d384eacd9bad7d916eb8f705": [6],
                    "61e4931d87cb627df2a19b8bc5819b7b": [5],
                    "6c7e43619fe5e6963e8159cc84a28321": [5],
                    "73612fdabd337d5a8279acc30ce22d00": [6],
                    "7b3ce20a8e8cf3097bb9df270a7ae63a": [5],
                    "816b147dcf3305839f723a131b9ad6af": [5],
                    "84000630d1b69a0fe870c94fb26a32bc": [5],
                    "8ce0d477f610ea18e2ea4fbbb46de857": [6],
                    "90bb41c1fbd7c71c05dbc8695320af71": [5],
                    "940576153c66af14a949fd19aedd5f5b": [5],
                    "976b121b46db6967854b9c1a6628396b": [5],
                    "9e58d3c72c7006b6f5800b623fbc9818": [6],
                    "ab05b4fb82e37c8cf5b1ac40d0a37fe9": [5],
                    "ad2ad2a70c3e0bf94ddef3f893e92291": [6],
                    "b20800a7faafd2808d6c888577a2ba1d": [5],
                    "bb54e4fa3906387218be10cff631a7c2": [6],
                    "bb81456ec79522bf02f34b02762f95e0": [6],
                    "c4fe9afce1cf3e83eb8518a9f5abc754": [5],
                    "c92d0679f769ac83fef2bb5eaac5d12a": [5],
                    "ce5f02ac408b7b5c500050190f549736": [5],
                    "e20c38f98b9830a40b851939ca7189d4": [6],
                    "eff8910cddcdff62e4741243099240d5": [5],
                    "f2e4d3da6556638b55df8ce509b094c2": [5],
                    "f67d274202366f6b976414c950ca14bd": [6],
                    "f6c389dcef63c1f214c30f66b66945c0": [6],
                    "ff5a6cc031dd2c98b8bccd4766af38c1": [6],
                },
                "details": {
                    "metric_configuration": {
                        "metric_name": "column.distinct_values.count",
                        "domain_kwargs": {"column": "rate_code_id"},
                        "metric_value_kwargs": None,
                        "metric_dependencies": None,
                    },
                    "num_batches": 36,
                },
            }
        },
        Domain(domain_type="column", domain_kwargs={"column": "store_and_fwd_flag",}): {
            "$parameter.column_distinct_values.count": {
                "value": [
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                    2,
                ],
                "attributed_value": {
                    "0327cfb13205ec8512e1c28e438ab43b": [2],
                    "08085632aff9ce4cebbb8023049e1aec": [2],
                    "0808e185a52825d22356de2fe00a8f5f": [2],
                    "33d910f95326c0c7dfe7536d1cfeba51": [2],
                    "3692b23382fd4734215465251290c65b": [2],
                    "44c1b1947c9049e7db62c5320dde4c63": [2],
                    "47157bdaf05a7992473cd699cabaef74": [2],
                    "562969eaef9c843cb4531aecbc13bbcb": [2],
                    "569a4a80bf434c888593c651dbf2f157": [2],
                    "57c04d62ada3a102248b48f34c755159": [2],
                    "58ce3b40d384eacd9bad7d916eb8f705": [2],
                    "61e4931d87cb627df2a19b8bc5819b7b": [2],
                    "6c7e43619fe5e6963e8159cc84a28321": [2],
                    "73612fdabd337d5a8279acc30ce22d00": [2],
                    "7b3ce20a8e8cf3097bb9df270a7ae63a": [2],
                    "816b147dcf3305839f723a131b9ad6af": [2],
                    "84000630d1b69a0fe870c94fb26a32bc": [2],
                    "8ce0d477f610ea18e2ea4fbbb46de857": [2],
                    "90bb41c1fbd7c71c05dbc8695320af71": [2],
                    "940576153c66af14a949fd19aedd5f5b": [2],
                    "976b121b46db6967854b9c1a6628396b": [2],
                    "9e58d3c72c7006b6f5800b623fbc9818": [2],
                    "ab05b4fb82e37c8cf5b1ac40d0a37fe9": [2],
                    "ad2ad2a70c3e0bf94ddef3f893e92291": [2],
                    "b20800a7faafd2808d6c888577a2ba1d": [2],
                    "bb54e4fa3906387218be10cff631a7c2": [2],
                    "bb81456ec79522bf02f34b02762f95e0": [2],
                    "c4fe9afce1cf3e83eb8518a9f5abc754": [2],
                    "c92d0679f769ac83fef2bb5eaac5d12a": [2],
                    "ce5f02ac408b7b5c500050190f549736": [2],
                    "e20c38f98b9830a40b851939ca7189d4": [2],
                    "eff8910cddcdff62e4741243099240d5": [2],
                    "f2e4d3da6556638b55df8ce509b094c2": [2],
                    "f67d274202366f6b976414c950ca14bd": [2],
                    "f6c389dcef63c1f214c30f66b66945c0": [2],
                    "ff5a6cc031dd2c98b8bccd4766af38c1": [2],
                },
                "details": {
                    "metric_configuration": {
                        "metric_name": "column.distinct_values.count",
                        "domain_kwargs": {"column": "store_and_fwd_flag"},
                        "metric_value_kwargs": None,
                        "metric_dependencies": None,
                    },
                    "num_batches": 36,
                },
            }
        },
        Domain(domain_type="column", domain_kwargs={"column": "pickup_location_id",}): {
            "$parameter.column_distinct_values.count": {
                "value": [
                    151,
                    146,
                    155,
                    144,
                    150,
                    136,
                    134,
                    118,
                    124,
                    195,
                    141,
                    144,
                    137,
                    208,
                    157,
                    187,
                    199,
                    211,
                    145,
                    209,
                    138,
                    143,
                    193,
                    214,
                    154,
                    151,
                    154,
                    119,
                    118,
                    155,
                    133,
                    142,
                    133,
                    146,
                    132,
                    212,
                ],
                "attributed_value": {
                    "0327cfb13205ec8512e1c28e438ab43b": [151],
                    "08085632aff9ce4cebbb8023049e1aec": [146],
                    "0808e185a52825d22356de2fe00a8f5f": [155],
                    "33d910f95326c0c7dfe7536d1cfeba51": [144],
                    "3692b23382fd4734215465251290c65b": [150],
                    "44c1b1947c9049e7db62c5320dde4c63": [136],
                    "47157bdaf05a7992473cd699cabaef74": [134],
                    "562969eaef9c843cb4531aecbc13bbcb": [118],
                    "569a4a80bf434c888593c651dbf2f157": [124],
                    "57c04d62ada3a102248b48f34c755159": [195],
                    "58ce3b40d384eacd9bad7d916eb8f705": [141],
                    "61e4931d87cb627df2a19b8bc5819b7b": [144],
                    "6c7e43619fe5e6963e8159cc84a28321": [137],
                    "73612fdabd337d5a8279acc30ce22d00": [208],
                    "7b3ce20a8e8cf3097bb9df270a7ae63a": [157],
                    "816b147dcf3305839f723a131b9ad6af": [187],
                    "84000630d1b69a0fe870c94fb26a32bc": [199],
                    "8ce0d477f610ea18e2ea4fbbb46de857": [211],
                    "90bb41c1fbd7c71c05dbc8695320af71": [145],
                    "940576153c66af14a949fd19aedd5f5b": [209],
                    "976b121b46db6967854b9c1a6628396b": [138],
                    "9e58d3c72c7006b6f5800b623fbc9818": [143],
                    "ab05b4fb82e37c8cf5b1ac40d0a37fe9": [193],
                    "ad2ad2a70c3e0bf94ddef3f893e92291": [214],
                    "b20800a7faafd2808d6c888577a2ba1d": [154],
                    "bb54e4fa3906387218be10cff631a7c2": [151],
                    "bb81456ec79522bf02f34b02762f95e0": [154],
                    "c4fe9afce1cf3e83eb8518a9f5abc754": [119],
                    "c92d0679f769ac83fef2bb5eaac5d12a": [118],
                    "ce5f02ac408b7b5c500050190f549736": [155],
                    "e20c38f98b9830a40b851939ca7189d4": [133],
                    "eff8910cddcdff62e4741243099240d5": [142],
                    "f2e4d3da6556638b55df8ce509b094c2": [133],
                    "f67d274202366f6b976414c950ca14bd": [146],
                    "f6c389dcef63c1f214c30f66b66945c0": [132],
                    "ff5a6cc031dd2c98b8bccd4766af38c1": [212],
                },
                "details": {
                    "metric_configuration": {
                        "metric_name": "column.distinct_values.count",
                        "domain_kwargs": {"column": "pickup_location_id"},
                        "metric_value_kwargs": None,
                        "metric_dependencies": None,
                    },
                    "num_batches": 36,
                },
            }
        },
        Domain(
            domain_type="column",
            domain_kwargs={
                "column": "dropoff_location_id",
            },
        ): {
            "$parameter.column_distinct_values.count": {
                "value": [
                    199,
                    192,
                    205,
                    203,
                    204,
                    203,
                    203,
                    197,
                    196,
                    222,
                    205,
                    198,
                    202,
                    234,
                    207,
                    230,
                    224,
                    238,
                    205,
                    232,
                    196,
                    206,
                    224,
                    237,
                    205,
                    197,
                    217,
                    200,
                    184,
                    213,
                    204,
                    206,
                    202,
                    204,
                    190,
                    233,
                ],
                "attributed_value": {
                    "0327cfb13205ec8512e1c28e438ab43b": [199],
                    "08085632aff9ce4cebbb8023049e1aec": [192],
                    "0808e185a52825d22356de2fe00a8f5f": [205],
                    "33d910f95326c0c7dfe7536d1cfeba51": [203],
                    "3692b23382fd4734215465251290c65b": [204],
                    "44c1b1947c9049e7db62c5320dde4c63": [203],
                    "47157bdaf05a7992473cd699cabaef74": [203],
                    "562969eaef9c843cb4531aecbc13bbcb": [197],
                    "569a4a80bf434c888593c651dbf2f157": [196],
                    "57c04d62ada3a102248b48f34c755159": [222],
                    "58ce3b40d384eacd9bad7d916eb8f705": [205],
                    "61e4931d87cb627df2a19b8bc5819b7b": [198],
                    "6c7e43619fe5e6963e8159cc84a28321": [202],
                    "73612fdabd337d5a8279acc30ce22d00": [234],
                    "7b3ce20a8e8cf3097bb9df270a7ae63a": [207],
                    "816b147dcf3305839f723a131b9ad6af": [230],
                    "84000630d1b69a0fe870c94fb26a32bc": [224],
                    "8ce0d477f610ea18e2ea4fbbb46de857": [238],
                    "90bb41c1fbd7c71c05dbc8695320af71": [205],
                    "940576153c66af14a949fd19aedd5f5b": [232],
                    "976b121b46db6967854b9c1a6628396b": [196],
                    "9e58d3c72c7006b6f5800b623fbc9818": [206],
                    "ab05b4fb82e37c8cf5b1ac40d0a37fe9": [224],
                    "ad2ad2a70c3e0bf94ddef3f893e92291": [237],
                    "b20800a7faafd2808d6c888577a2ba1d": [205],
                    "bb54e4fa3906387218be10cff631a7c2": [197],
                    "bb81456ec79522bf02f34b02762f95e0": [217],
                    "c4fe9afce1cf3e83eb8518a9f5abc754": [200],
                    "c92d0679f769ac83fef2bb5eaac5d12a": [184],
                    "ce5f02ac408b7b5c500050190f549736": [213],
                    "e20c38f98b9830a40b851939ca7189d4": [204],
                    "eff8910cddcdff62e4741243099240d5": [206],
                    "f2e4d3da6556638b55df8ce509b094c2": [202],
                    "f67d274202366f6b976414c950ca14bd": [204],
                    "f6c389dcef63c1f214c30f66b66945c0": [190],
                    "ff5a6cc031dd2c98b8bccd4766af38c1": [233],
                },
                "details": {
                    "metric_configuration": {
                        "metric_name": "column.distinct_values.count",
                        "domain_kwargs": {"column": "dropoff_location_id"},
                        "metric_value_kwargs": None,
                        "metric_dependencies": None,
                    },
                    "num_batches": 36,
                },
            }
        },
        Domain(domain_type="column", domain_kwargs={"column": "payment_type",}): {
            "$parameter.column_distinct_values.count": {
                "value": [
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                    4,
                ],
                "attributed_value": {
                    "0327cfb13205ec8512e1c28e438ab43b": [4],
                    "08085632aff9ce4cebbb8023049e1aec": [4],
                    "0808e185a52825d22356de2fe00a8f5f": [4],
                    "33d910f95326c0c7dfe7536d1cfeba51": [4],
                    "3692b23382fd4734215465251290c65b": [4],
                    "44c1b1947c9049e7db62c5320dde4c63": [4],
                    "47157bdaf05a7992473cd699cabaef74": [4],
                    "562969eaef9c843cb4531aecbc13bbcb": [4],
                    "569a4a80bf434c888593c651dbf2f157": [4],
                    "57c04d62ada3a102248b48f34c755159": [4],
                    "58ce3b40d384eacd9bad7d916eb8f705": [4],
                    "61e4931d87cb627df2a19b8bc5819b7b": [4],
                    "6c7e43619fe5e6963e8159cc84a28321": [4],
                    "73612fdabd337d5a8279acc30ce22d00": [4],
                    "7b3ce20a8e8cf3097bb9df270a7ae63a": [4],
                    "816b147dcf3305839f723a131b9ad6af": [4],
                    "84000630d1b69a0fe870c94fb26a32bc": [4],
                    "8ce0d477f610ea18e2ea4fbbb46de857": [4],
                    "90bb41c1fbd7c71c05dbc8695320af71": [4],
                    "940576153c66af14a949fd19aedd5f5b": [4],
                    "976b121b46db6967854b9c1a6628396b": [4],
                    "9e58d3c72c7006b6f5800b623fbc9818": [4],
                    "ab05b4fb82e37c8cf5b1ac40d0a37fe9": [4],
                    "ad2ad2a70c3e0bf94ddef3f893e92291": [4],
                    "b20800a7faafd2808d6c888577a2ba1d": [4],
                    "bb54e4fa3906387218be10cff631a7c2": [4],
                    "bb81456ec79522bf02f34b02762f95e0": [4],
                    "c4fe9afce1cf3e83eb8518a9f5abc754": [4],
                    "c92d0679f769ac83fef2bb5eaac5d12a": [4],
                    "ce5f02ac408b7b5c500050190f549736": [4],
                    "e20c38f98b9830a40b851939ca7189d4": [4],
                    "eff8910cddcdff62e4741243099240d5": [4],
                    "f2e4d3da6556638b55df8ce509b094c2": [4],
                    "f67d274202366f6b976414c950ca14bd": [4],
                    "f6c389dcef63c1f214c30f66b66945c0": [4],
                    "ff5a6cc031dd2c98b8bccd4766af38c1": [4],
                },
                "details": {
                    "metric_configuration": {
                        "metric_name": "column.distinct_values.count",
                        "domain_kwargs": {"column": "payment_type"},
                        "metric_value_kwargs": None,
                        "metric_dependencies": None,
                    },
                    "num_batches": 36,
                },
            }
        },
        Domain(domain_type="column", domain_kwargs={"column": "fare_amount",}): {
            "$parameter.column_distinct_values.count": {
                "value": [
                    187,
                    170,
                    201,
                    246,
                    252,
                    176,
                    169,
                    148,
                    161,
                    568,
                    184,
                    246,
                    178,
                    797,
                    296,
                    552,
                    588,
                    813,
                    202,
                    575,
                    170,
                    184,
                    571,
                    1500,
                    248,
                    199,
                    253,
                    153,
                    153,
                    238,
                    161,
                    259,
                    168,
                    267,
                    156,
                    575,
                ],
                "attributed_value": {
                    "0327cfb13205ec8512e1c28e438ab43b": [187],
                    "08085632aff9ce4cebbb8023049e1aec": [170],
                    "0808e185a52825d22356de2fe00a8f5f": [201],
                    "33d910f95326c0c7dfe7536d1cfeba51": [246],
                    "3692b23382fd4734215465251290c65b": [252],
                    "44c1b1947c9049e7db62c5320dde4c63": [176],
                    "47157bdaf05a7992473cd699cabaef74": [169],
                    "562969eaef9c843cb4531aecbc13bbcb": [148],
                    "569a4a80bf434c888593c651dbf2f157": [161],
                    "57c04d62ada3a102248b48f34c755159": [568],
                    "58ce3b40d384eacd9bad7d916eb8f705": [184],
                    "61e4931d87cb627df2a19b8bc5819b7b": [246],
                    "6c7e43619fe5e6963e8159cc84a28321": [178],
                    "73612fdabd337d5a8279acc30ce22d00": [797],
                    "7b3ce20a8e8cf3097bb9df270a7ae63a": [296],
                    "816b147dcf3305839f723a131b9ad6af": [552],
                    "84000630d1b69a0fe870c94fb26a32bc": [588],
                    "8ce0d477f610ea18e2ea4fbbb46de857": [813],
                    "90bb41c1fbd7c71c05dbc8695320af71": [202],
                    "940576153c66af14a949fd19aedd5f5b": [575],
                    "976b121b46db6967854b9c1a6628396b": [170],
                    "9e58d3c72c7006b6f5800b623fbc9818": [184],
                    "ab05b4fb82e37c8cf5b1ac40d0a37fe9": [571],
                    "ad2ad2a70c3e0bf94ddef3f893e92291": [1500],
                    "b20800a7faafd2808d6c888577a2ba1d": [248],
                    "bb54e4fa3906387218be10cff631a7c2": [199],
                    "bb81456ec79522bf02f34b02762f95e0": [253],
                    "c4fe9afce1cf3e83eb8518a9f5abc754": [153],
                    "c92d0679f769ac83fef2bb5eaac5d12a": [153],
                    "ce5f02ac408b7b5c500050190f549736": [238],
                    "e20c38f98b9830a40b851939ca7189d4": [161],
                    "eff8910cddcdff62e4741243099240d5": [259],
                    "f2e4d3da6556638b55df8ce509b094c2": [168],
                    "f67d274202366f6b976414c950ca14bd": [267],
                    "f6c389dcef63c1f214c30f66b66945c0": [156],
                    "ff5a6cc031dd2c98b8bccd4766af38c1": [575],
                },
                "details": {
                    "metric_configuration": {
                        "metric_name": "column.distinct_values.count",
                        "domain_kwargs": {"column": "fare_amount"},
                        "metric_value_kwargs": None,
                        "metric_dependencies": None,
                    },
                    "num_batches": 36,
                },
            }
        },
        Domain(domain_type="column", domain_kwargs={"column": "extra",}): {
            "$parameter.column_distinct_values.count": {
                "value": [
                    8,
                    7,
                    10,
                    16,
                    13,
                    7,
                    6,
                    6,
                    6,
                    10,
                    6,
                    12,
                    12,
                    10,
                    14,
                    11,
                    10,
                    10,
                    12,
                    12,
                    10,
                    11,
                    11,
                    11,
                    13,
                    6,
                    14,
                    6,
                    6,
                    12,
                    4,
                    12,
                    5,
                    15,
                    5,
                    13,
                ],
                "attributed_value": {
                    "0327cfb13205ec8512e1c28e438ab43b": [8],
                    "08085632aff9ce4cebbb8023049e1aec": [7],
                    "0808e185a52825d22356de2fe00a8f5f": [10],
                    "33d910f95326c0c7dfe7536d1cfeba51": [16],
                    "3692b23382fd4734215465251290c65b": [13],
                    "44c1b1947c9049e7db62c5320dde4c63": [7],
                    "47157bdaf05a7992473cd699cabaef74": [6],
                    "562969eaef9c843cb4531aecbc13bbcb": [6],
                    "569a4a80bf434c888593c651dbf2f157": [6],
                    "57c04d62ada3a102248b48f34c755159": [10],
                    "58ce3b40d384eacd9bad7d916eb8f705": [6],
                    "61e4931d87cb627df2a19b8bc5819b7b": [12],
                    "6c7e43619fe5e6963e8159cc84a28321": [12],
                    "73612fdabd337d5a8279acc30ce22d00": [10],
                    "7b3ce20a8e8cf3097bb9df270a7ae63a": [14],
                    "816b147dcf3305839f723a131b9ad6af": [11],
                    "84000630d1b69a0fe870c94fb26a32bc": [10],
                    "8ce0d477f610ea18e2ea4fbbb46de857": [10],
                    "90bb41c1fbd7c71c05dbc8695320af71": [12],
                    "940576153c66af14a949fd19aedd5f5b": [12],
                    "976b121b46db6967854b9c1a6628396b": [10],
                    "9e58d3c72c7006b6f5800b623fbc9818": [11],
                    "ab05b4fb82e37c8cf5b1ac40d0a37fe9": [11],
                    "ad2ad2a70c3e0bf94ddef3f893e92291": [11],
                    "b20800a7faafd2808d6c888577a2ba1d": [13],
                    "bb54e4fa3906387218be10cff631a7c2": [6],
                    "bb81456ec79522bf02f34b02762f95e0": [14],
                    "c4fe9afce1cf3e83eb8518a9f5abc754": [6],
                    "c92d0679f769ac83fef2bb5eaac5d12a": [6],
                    "ce5f02ac408b7b5c500050190f549736": [12],
                    "e20c38f98b9830a40b851939ca7189d4": [4],
                    "eff8910cddcdff62e4741243099240d5": [12],
                    "f2e4d3da6556638b55df8ce509b094c2": [5],
                    "f67d274202366f6b976414c950ca14bd": [15],
                    "f6c389dcef63c1f214c30f66b66945c0": [5],
                    "ff5a6cc031dd2c98b8bccd4766af38c1": [13],
                },
                "details": {
                    "metric_configuration": {
                        "metric_name": "column.distinct_values.count",
                        "domain_kwargs": {"column": "extra"},
                        "metric_value_kwargs": None,
                        "metric_dependencies": None,
                    },
                    "num_batches": 36,
                },
            }
        },
        Domain(domain_type="column", domain_kwargs={"column": "mta_tax",}): {
            "$parameter.column_distinct_values.count": {
                "value": [
                    4,
                    3,
                    3,
                    3,
                    4,
                    3,
                    3,
                    3,
                    3,
                    4,
                    3,
                    4,
                    3,
                    3,
                    3,
                    4,
                    3,
                    3,
                    3,
                    3,
                    3,
                    4,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                ],
                "attributed_value": {
                    "0327cfb13205ec8512e1c28e438ab43b": [4],
                    "08085632aff9ce4cebbb8023049e1aec": [3],
                    "0808e185a52825d22356de2fe00a8f5f": [3],
                    "33d910f95326c0c7dfe7536d1cfeba51": [3],
                    "3692b23382fd4734215465251290c65b": [4],
                    "44c1b1947c9049e7db62c5320dde4c63": [3],
                    "47157bdaf05a7992473cd699cabaef74": [3],
                    "562969eaef9c843cb4531aecbc13bbcb": [3],
                    "569a4a80bf434c888593c651dbf2f157": [3],
                    "57c04d62ada3a102248b48f34c755159": [4],
                    "58ce3b40d384eacd9bad7d916eb8f705": [3],
                    "61e4931d87cb627df2a19b8bc5819b7b": [4],
                    "6c7e43619fe5e6963e8159cc84a28321": [3],
                    "73612fdabd337d5a8279acc30ce22d00": [3],
                    "7b3ce20a8e8cf3097bb9df270a7ae63a": [3],
                    "816b147dcf3305839f723a131b9ad6af": [4],
                    "84000630d1b69a0fe870c94fb26a32bc": [3],
                    "8ce0d477f610ea18e2ea4fbbb46de857": [3],
                    "90bb41c1fbd7c71c05dbc8695320af71": [3],
                    "940576153c66af14a949fd19aedd5f5b": [3],
                    "976b121b46db6967854b9c1a6628396b": [3],
                    "9e58d3c72c7006b6f5800b623fbc9818": [4],
                    "ab05b4fb82e37c8cf5b1ac40d0a37fe9": [3],
                    "ad2ad2a70c3e0bf94ddef3f893e92291": [3],
                    "b20800a7faafd2808d6c888577a2ba1d": [3],
                    "bb54e4fa3906387218be10cff631a7c2": [3],
                    "bb81456ec79522bf02f34b02762f95e0": [3],
                    "c4fe9afce1cf3e83eb8518a9f5abc754": [3],
                    "c92d0679f769ac83fef2bb5eaac5d12a": [3],
                    "ce5f02ac408b7b5c500050190f549736": [3],
                    "e20c38f98b9830a40b851939ca7189d4": [3],
                    "eff8910cddcdff62e4741243099240d5": [3],
                    "f2e4d3da6556638b55df8ce509b094c2": [3],
                    "f67d274202366f6b976414c950ca14bd": [3],
                    "f6c389dcef63c1f214c30f66b66945c0": [3],
                    "ff5a6cc031dd2c98b8bccd4766af38c1": [3],
                },
                "details": {
                    "metric_configuration": {
                        "metric_name": "column.distinct_values.count",
                        "domain_kwargs": {"column": "mta_tax"},
                        "metric_value_kwargs": None,
                        "metric_dependencies": None,
                    },
                    "num_batches": 36,
                },
            }
        },
        Domain(domain_type="column", domain_kwargs={"column": "tip_amount",}): {
            "$parameter.column_distinct_values.count": {
                "value": [
                    535,
                    555,
                    597,
                    591,
                    606,
                    567,
                    576,
                    530,
                    539,
                    505,
                    601,
                    599,
                    596,
                    469,
                    560,
                    515,
                    522,
                    558,
                    601,
                    530,
                    612,
                    606,
                    503,
                    466,
                    608,
                    600,
                    595,
                    574,
                    532,
                    579,
                    559,
                    572,
                    557,
                    576,
                    573,
                    539,
                ],
                "attributed_value": {
                    "0327cfb13205ec8512e1c28e438ab43b": [535],
                    "08085632aff9ce4cebbb8023049e1aec": [555],
                    "0808e185a52825d22356de2fe00a8f5f": [597],
                    "33d910f95326c0c7dfe7536d1cfeba51": [591],
                    "3692b23382fd4734215465251290c65b": [606],
                    "44c1b1947c9049e7db62c5320dde4c63": [567],
                    "47157bdaf05a7992473cd699cabaef74": [576],
                    "562969eaef9c843cb4531aecbc13bbcb": [530],
                    "569a4a80bf434c888593c651dbf2f157": [539],
                    "57c04d62ada3a102248b48f34c755159": [505],
                    "58ce3b40d384eacd9bad7d916eb8f705": [601],
                    "61e4931d87cb627df2a19b8bc5819b7b": [599],
                    "6c7e43619fe5e6963e8159cc84a28321": [596],
                    "73612fdabd337d5a8279acc30ce22d00": [469],
                    "7b3ce20a8e8cf3097bb9df270a7ae63a": [560],
                    "816b147dcf3305839f723a131b9ad6af": [515],
                    "84000630d1b69a0fe870c94fb26a32bc": [522],
                    "8ce0d477f610ea18e2ea4fbbb46de857": [558],
                    "90bb41c1fbd7c71c05dbc8695320af71": [601],
                    "940576153c66af14a949fd19aedd5f5b": [530],
                    "976b121b46db6967854b9c1a6628396b": [612],
                    "9e58d3c72c7006b6f5800b623fbc9818": [606],
                    "ab05b4fb82e37c8cf5b1ac40d0a37fe9": [503],
                    "ad2ad2a70c3e0bf94ddef3f893e92291": [466],
                    "b20800a7faafd2808d6c888577a2ba1d": [608],
                    "bb54e4fa3906387218be10cff631a7c2": [600],
                    "bb81456ec79522bf02f34b02762f95e0": [595],
                    "c4fe9afce1cf3e83eb8518a9f5abc754": [574],
                    "c92d0679f769ac83fef2bb5eaac5d12a": [532],
                    "ce5f02ac408b7b5c500050190f549736": [579],
                    "e20c38f98b9830a40b851939ca7189d4": [559],
                    "eff8910cddcdff62e4741243099240d5": [572],
                    "f2e4d3da6556638b55df8ce509b094c2": [557],
                    "f67d274202366f6b976414c950ca14bd": [576],
                    "f6c389dcef63c1f214c30f66b66945c0": [573],
                    "ff5a6cc031dd2c98b8bccd4766af38c1": [539],
                },
                "details": {
                    "metric_configuration": {
                        "metric_name": "column.distinct_values.count",
                        "domain_kwargs": {"column": "tip_amount"},
                        "metric_value_kwargs": None,
                        "metric_dependencies": None,
                    },
                    "num_batches": 36,
                },
            }
        },
        Domain(domain_type="column", domain_kwargs={"column": "tolls_amount",}): {
            "$parameter.column_distinct_values.count": {
                "value": [
                    22,
                    19,
                    26,
                    32,
                    26,
                    26,
                    24,
                    24,
                    28,
                    22,
                    26,
                    23,
                    27,
                    19,
                    20,
                    16,
                    20,
                    30,
                    20,
                    22,
                    27,
                    23,
                    21,
                    22,
                    28,
                    24,
                    27,
                    21,
                    20,
                    31,
                    25,
                    27,
                    23,
                    29,
                    24,
                    27,
                ],
                "attributed_value": {
                    "0327cfb13205ec8512e1c28e438ab43b": [22],
                    "08085632aff9ce4cebbb8023049e1aec": [19],
                    "0808e185a52825d22356de2fe00a8f5f": [26],
                    "33d910f95326c0c7dfe7536d1cfeba51": [32],
                    "3692b23382fd4734215465251290c65b": [26],
                    "44c1b1947c9049e7db62c5320dde4c63": [26],
                    "47157bdaf05a7992473cd699cabaef74": [24],
                    "562969eaef9c843cb4531aecbc13bbcb": [24],
                    "569a4a80bf434c888593c651dbf2f157": [28],
                    "57c04d62ada3a102248b48f34c755159": [22],
                    "58ce3b40d384eacd9bad7d916eb8f705": [26],
                    "61e4931d87cb627df2a19b8bc5819b7b": [23],
                    "6c7e43619fe5e6963e8159cc84a28321": [27],
                    "73612fdabd337d5a8279acc30ce22d00": [19],
                    "7b3ce20a8e8cf3097bb9df270a7ae63a": [20],
                    "816b147dcf3305839f723a131b9ad6af": [16],
                    "84000630d1b69a0fe870c94fb26a32bc": [20],
                    "8ce0d477f610ea18e2ea4fbbb46de857": [30],
                    "90bb41c1fbd7c71c05dbc8695320af71": [20],
                    "940576153c66af14a949fd19aedd5f5b": [22],
                    "976b121b46db6967854b9c1a6628396b": [27],
                    "9e58d3c72c7006b6f5800b623fbc9818": [23],
                    "ab05b4fb82e37c8cf5b1ac40d0a37fe9": [21],
                    "ad2ad2a70c3e0bf94ddef3f893e92291": [22],
                    "b20800a7faafd2808d6c888577a2ba1d": [28],
                    "bb54e4fa3906387218be10cff631a7c2": [24],
                    "bb81456ec79522bf02f34b02762f95e0": [27],
                    "c4fe9afce1cf3e83eb8518a9f5abc754": [21],
                    "c92d0679f769ac83fef2bb5eaac5d12a": [20],
                    "ce5f02ac408b7b5c500050190f549736": [31],
                    "e20c38f98b9830a40b851939ca7189d4": [25],
                    "eff8910cddcdff62e4741243099240d5": [27],
                    "f2e4d3da6556638b55df8ce509b094c2": [23],
                    "f67d274202366f6b976414c950ca14bd": [29],
                    "f6c389dcef63c1f214c30f66b66945c0": [24],
                    "ff5a6cc031dd2c98b8bccd4766af38c1": [27],
                },
                "details": {
                    "metric_configuration": {
                        "metric_name": "column.distinct_values.count",
                        "domain_kwargs": {"column": "tolls_amount"},
                        "metric_value_kwargs": None,
                        "metric_dependencies": None,
                    },
                    "num_batches": 36,
                },
            }
        },
        Domain(
            domain_type="column",
            domain_kwargs={
                "column": "improvement_surcharge",
            },
        ): {
            "$parameter.column_distinct_values.count": {
                "value": [
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                ],
                "attributed_value": {
                    "0327cfb13205ec8512e1c28e438ab43b": [3],
                    "08085632aff9ce4cebbb8023049e1aec": [3],
                    "0808e185a52825d22356de2fe00a8f5f": [3],
                    "33d910f95326c0c7dfe7536d1cfeba51": [3],
                    "3692b23382fd4734215465251290c65b": [3],
                    "44c1b1947c9049e7db62c5320dde4c63": [3],
                    "47157bdaf05a7992473cd699cabaef74": [3],
                    "562969eaef9c843cb4531aecbc13bbcb": [3],
                    "569a4a80bf434c888593c651dbf2f157": [3],
                    "57c04d62ada3a102248b48f34c755159": [3],
                    "58ce3b40d384eacd9bad7d916eb8f705": [3],
                    "61e4931d87cb627df2a19b8bc5819b7b": [3],
                    "6c7e43619fe5e6963e8159cc84a28321": [3],
                    "73612fdabd337d5a8279acc30ce22d00": [3],
                    "7b3ce20a8e8cf3097bb9df270a7ae63a": [3],
                    "816b147dcf3305839f723a131b9ad6af": [3],
                    "84000630d1b69a0fe870c94fb26a32bc": [3],
                    "8ce0d477f610ea18e2ea4fbbb46de857": [3],
                    "90bb41c1fbd7c71c05dbc8695320af71": [3],
                    "940576153c66af14a949fd19aedd5f5b": [3],
                    "976b121b46db6967854b9c1a6628396b": [3],
                    "9e58d3c72c7006b6f5800b623fbc9818": [3],
                    "ab05b4fb82e37c8cf5b1ac40d0a37fe9": [3],
                    "ad2ad2a70c3e0bf94ddef3f893e92291": [3],
                    "b20800a7faafd2808d6c888577a2ba1d": [3],
                    "bb54e4fa3906387218be10cff631a7c2": [3],
                    "bb81456ec79522bf02f34b02762f95e0": [3],
                    "c4fe9afce1cf3e83eb8518a9f5abc754": [3],
                    "c92d0679f769ac83fef2bb5eaac5d12a": [3],
                    "ce5f02ac408b7b5c500050190f549736": [3],
                    "e20c38f98b9830a40b851939ca7189d4": [3],
                    "eff8910cddcdff62e4741243099240d5": [3],
                    "f2e4d3da6556638b55df8ce509b094c2": [3],
                    "f67d274202366f6b976414c950ca14bd": [3],
                    "f6c389dcef63c1f214c30f66b66945c0": [3],
                    "ff5a6cc031dd2c98b8bccd4766af38c1": [3],
                },
                "details": {
                    "metric_configuration": {
                        "metric_name": "column.distinct_values.count",
                        "domain_kwargs": {"column": "improvement_surcharge"},
                        "metric_value_kwargs": None,
                        "metric_dependencies": None,
                    },
                    "num_batches": 36,
                },
            }
        },
        Domain(domain_type="column", domain_kwargs={"column": "total_amount",}): {
            "$parameter.column_distinct_values.count": {
                "value": [
                    942,
                    972,
                    1016,
                    1070,
                    1060,
                    966,
                    973,
                    884,
                    905,
                    1161,
                    1000,
                    1068,
                    1012,
                    1387,
                    1060,
                    1154,
                    1164,
                    1440,
                    1016,
                    1153,
                    1026,
                    1044,
                    1154,
                    2018,
                    1073,
                    1043,
                    1077,
                    953,
                    898,
                    1047,
                    945,
                    1037,
                    969,
                    1036,
                    942,
                    1154,
                ],
                "attributed_value": {
                    "0327cfb13205ec8512e1c28e438ab43b": [942],
                    "08085632aff9ce4cebbb8023049e1aec": [972],
                    "0808e185a52825d22356de2fe00a8f5f": [1016],
                    "33d910f95326c0c7dfe7536d1cfeba51": [1070],
                    "3692b23382fd4734215465251290c65b": [1060],
                    "44c1b1947c9049e7db62c5320dde4c63": [966],
                    "47157bdaf05a7992473cd699cabaef74": [973],
                    "562969eaef9c843cb4531aecbc13bbcb": [884],
                    "569a4a80bf434c888593c651dbf2f157": [905],
                    "57c04d62ada3a102248b48f34c755159": [1161],
                    "58ce3b40d384eacd9bad7d916eb8f705": [1000],
                    "61e4931d87cb627df2a19b8bc5819b7b": [1068],
                    "6c7e43619fe5e6963e8159cc84a28321": [1012],
                    "73612fdabd337d5a8279acc30ce22d00": [1387],
                    "7b3ce20a8e8cf3097bb9df270a7ae63a": [1060],
                    "816b147dcf3305839f723a131b9ad6af": [1154],
                    "84000630d1b69a0fe870c94fb26a32bc": [1164],
                    "8ce0d477f610ea18e2ea4fbbb46de857": [1440],
                    "90bb41c1fbd7c71c05dbc8695320af71": [1016],
                    "940576153c66af14a949fd19aedd5f5b": [1153],
                    "976b121b46db6967854b9c1a6628396b": [1026],
                    "9e58d3c72c7006b6f5800b623fbc9818": [1044],
                    "ab05b4fb82e37c8cf5b1ac40d0a37fe9": [1154],
                    "ad2ad2a70c3e0bf94ddef3f893e92291": [2018],
                    "b20800a7faafd2808d6c888577a2ba1d": [1073],
                    "bb54e4fa3906387218be10cff631a7c2": [1043],
                    "bb81456ec79522bf02f34b02762f95e0": [1077],
                    "c4fe9afce1cf3e83eb8518a9f5abc754": [953],
                    "c92d0679f769ac83fef2bb5eaac5d12a": [898],
                    "ce5f02ac408b7b5c500050190f549736": [1047],
                    "e20c38f98b9830a40b851939ca7189d4": [945],
                    "eff8910cddcdff62e4741243099240d5": [1037],
                    "f2e4d3da6556638b55df8ce509b094c2": [969],
                    "f67d274202366f6b976414c950ca14bd": [1036],
                    "f6c389dcef63c1f214c30f66b66945c0": [942],
                    "ff5a6cc031dd2c98b8bccd4766af38c1": [1154],
                },
                "details": {
                    "metric_configuration": {
                        "metric_name": "column.distinct_values.count",
                        "domain_kwargs": {"column": "total_amount"},
                        "metric_value_kwargs": None,
                        "metric_dependencies": None,
                    },
                    "num_batches": 36,
                },
            }
        },
        Domain(
            domain_type="column",
            domain_kwargs={
                "column": "congestion_surcharge",
            },
        ): {
            "$parameter.column_distinct_values.count": {
                "value": [
                    1,
                    0,
                    3,
                    3,
                    3,
                    0,
                    0,
                    0,
                    0,
                    3,
                    0,
                    3,
                    4,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    3,
                    0,
                    3,
                    0,
                    0,
                    3,
                    0,
                    4,
                    0,
                    3,
                    0,
                    3,
                ],
                "attributed_value": {
                    "0327cfb13205ec8512e1c28e438ab43b": [1],
                    "08085632aff9ce4cebbb8023049e1aec": [0],
                    "0808e185a52825d22356de2fe00a8f5f": [3],
                    "33d910f95326c0c7dfe7536d1cfeba51": [3],
                    "3692b23382fd4734215465251290c65b": [3],
                    "44c1b1947c9049e7db62c5320dde4c63": [0],
                    "47157bdaf05a7992473cd699cabaef74": [0],
                    "562969eaef9c843cb4531aecbc13bbcb": [0],
                    "569a4a80bf434c888593c651dbf2f157": [0],
                    "57c04d62ada3a102248b48f34c755159": [3],
                    "58ce3b40d384eacd9bad7d916eb8f705": [0],
                    "61e4931d87cb627df2a19b8bc5819b7b": [3],
                    "6c7e43619fe5e6963e8159cc84a28321": [4],
                    "73612fdabd337d5a8279acc30ce22d00": [3],
                    "7b3ce20a8e8cf3097bb9df270a7ae63a": [3],
                    "816b147dcf3305839f723a131b9ad6af": [3],
                    "84000630d1b69a0fe870c94fb26a32bc": [3],
                    "8ce0d477f610ea18e2ea4fbbb46de857": [3],
                    "90bb41c1fbd7c71c05dbc8695320af71": [3],
                    "940576153c66af14a949fd19aedd5f5b": [3],
                    "976b121b46db6967854b9c1a6628396b": [3],
                    "9e58d3c72c7006b6f5800b623fbc9818": [3],
                    "ab05b4fb82e37c8cf5b1ac40d0a37fe9": [3],
                    "ad2ad2a70c3e0bf94ddef3f893e92291": [3],
                    "b20800a7faafd2808d6c888577a2ba1d": [3],
                    "bb54e4fa3906387218be10cff631a7c2": [0],
                    "bb81456ec79522bf02f34b02762f95e0": [3],
                    "c4fe9afce1cf3e83eb8518a9f5abc754": [0],
                    "c92d0679f769ac83fef2bb5eaac5d12a": [0],
                    "ce5f02ac408b7b5c500050190f549736": [3],
                    "e20c38f98b9830a40b851939ca7189d4": [0],
                    "eff8910cddcdff62e4741243099240d5": [4],
                    "f2e4d3da6556638b55df8ce509b094c2": [0],
                    "f67d274202366f6b976414c950ca14bd": [3],
                    "f6c389dcef63c1f214c30f66b66945c0": [0],
                    "ff5a6cc031dd2c98b8bccd4766af38c1": [3],
                },
                "details": {
                    "metric_configuration": {
                        "metric_name": "column.distinct_values.count",
                        "domain_kwargs": {"column": "congestion_surcharge"},
                        "metric_value_kwargs": None,
                        "metric_dependencies": None,
                    },
                    "num_batches": 36,
                },
            }
        },
    }

    expected_expect_table_row_count_to_be_between_expectation_configuration: ExpectationConfiguration = ExpectationConfiguration(
        **{
            "expectation_type": "expect_table_row_count_to_be_between",
            "kwargs": {
                "min_value": 10000,
                "max_value": 10000,
            },
            "meta": {
                "profiler_details": {
                    "metric_configuration": {
                        "metric_name": "table.row_count",
                        "domain_kwargs": {},
                        "metric_value_kwargs": None,
                        "metric_dependencies": None,
                    },
                    "num_batches": 36,
                },
            },
        },
    )

    expected_expect_column_unique_value_count_to_be_between_expectation_configuration_list: List[
        ExpectationConfiguration
    ] = [
        ExpectationConfiguration(
            **{
                "meta": {
                    "profiler_details": {
                        "metric_configuration": {
                            "metric_name": "column.distinct_values.count",
                            "domain_kwargs": {"column": "vendor_id"},
                            "metric_value_kwargs": None,
                            "metric_dependencies": None,
                        },
                        "num_batches": 36,
                    }
                },
                "expectation_type": "expect_column_unique_value_count_to_be_between",
                "kwargs": {
                    "strict_max": False,
                    "max_value": 3,
                    "strict_min": False,
                    "column": "vendor_id",
                    "min_value": 2,
                },
            }
        ),
        ExpectationConfiguration(
            **{
                "meta": {
                    "profiler_details": {
                        "metric_configuration": {
                            "metric_name": "column.distinct_values.count",
                            "domain_kwargs": {"column": "pickup_datetime"},
                            "metric_value_kwargs": None,
                            "metric_dependencies": None,
                        },
                        "num_batches": 36,
                    }
                },
                "expectation_type": "expect_column_unique_value_count_to_be_between",
                "kwargs": {
                    "strict_max": False,
                    "max_value": 9983,
                    "strict_min": False,
                    "column": "pickup_datetime",
                    "min_value": 9944,
                },
            }
        ),
        ExpectationConfiguration(
            **{
                "meta": {
                    "profiler_details": {
                        "metric_configuration": {
                            "metric_name": "column.distinct_values.count",
                            "domain_kwargs": {"column": "dropoff_datetime"},
                            "metric_value_kwargs": None,
                            "metric_dependencies": None,
                        },
                        "num_batches": 36,
                    }
                },
                "expectation_type": "expect_column_unique_value_count_to_be_between",
                "kwargs": {
                    "strict_max": False,
                    "max_value": 9985,
                    "strict_min": False,
                    "column": "dropoff_datetime",
                    "min_value": 9957,
                },
            }
        ),
        ExpectationConfiguration(
            **{
                "meta": {
                    "profiler_details": {
                        "metric_configuration": {
                            "metric_name": "column.distinct_values.count",
                            "domain_kwargs": {"column": "passenger_count"},
                            "metric_value_kwargs": None,
                            "metric_dependencies": None,
                        },
                        "num_batches": 36,
                    }
                },
                "expectation_type": "expect_column_unique_value_count_to_be_between",
                "kwargs": {
                    "strict_max": False,
                    "max_value": 8,
                    "strict_min": False,
                    "column": "passenger_count",
                    "min_value": 7,
                },
            }
        ),
        ExpectationConfiguration(
            **{
                "meta": {
                    "profiler_details": {
                        "metric_configuration": {
                            "metric_name": "column.distinct_values.count",
                            "domain_kwargs": {"column": "trip_distance"},
                            "metric_value_kwargs": None,
                            "metric_dependencies": None,
                        },
                        "num_batches": 36,
                    }
                },
                "expectation_type": "expect_column_unique_value_count_to_be_between",
                "kwargs": {
                    "strict_max": False,
                    "max_value": 1439,
                    "strict_min": False,
                    "column": "trip_distance",
                    "min_value": 1157,
                },
            }
        ),
        ExpectationConfiguration(
            **{
                "meta": {
                    "profiler_details": {
                        "metric_configuration": {
                            "metric_name": "column.distinct_values.count",
                            "domain_kwargs": {"column": "rate_code_id"},
                            "metric_value_kwargs": None,
                            "metric_dependencies": None,
                        },
                        "num_batches": 36,
                    }
                },
                "expectation_type": "expect_column_unique_value_count_to_be_between",
                "kwargs": {
                    "strict_max": False,
                    "max_value": 6,
                    "strict_min": False,
                    "column": "rate_code_id",
                    "min_value": 5,
                },
            }
        ),
        ExpectationConfiguration(
            **{
                "meta": {
                    "profiler_details": {
                        "metric_configuration": {
                            "metric_name": "column.distinct_values.count",
                            "domain_kwargs": {"column": "store_and_fwd_flag"},
                            "metric_value_kwargs": None,
                            "metric_dependencies": None,
                        },
                        "num_batches": 36,
                    }
                },
                "expectation_type": "expect_column_unique_value_count_to_be_between",
                "kwargs": {
                    "strict_max": False,
                    "max_value": 2,
                    "strict_min": False,
                    "column": "store_and_fwd_flag",
                    "min_value": 2,
                },
            }
        ),
        ExpectationConfiguration(
            **{
                "meta": {
                    "profiler_details": {
                        "metric_configuration": {
                            "metric_name": "column.distinct_values.count",
                            "domain_kwargs": {"column": "pickup_location_id"},
                            "metric_value_kwargs": None,
                            "metric_dependencies": None,
                        },
                        "num_batches": 36,
                    }
                },
                "expectation_type": "expect_column_unique_value_count_to_be_between",
                "kwargs": {
                    "strict_max": False,
                    "max_value": 212,
                    "strict_min": False,
                    "column": "pickup_location_id",
                    "min_value": 118,
                },
            }
        ),
        ExpectationConfiguration(
            **{
                "meta": {
                    "profiler_details": {
                        "metric_configuration": {
                            "metric_name": "column.distinct_values.count",
                            "domain_kwargs": {"column": "dropoff_location_id"},
                            "metric_value_kwargs": None,
                            "metric_dependencies": None,
                        },
                        "num_batches": 36,
                    }
                },
                "expectation_type": "expect_column_unique_value_count_to_be_between",
                "kwargs": {
                    "strict_max": False,
                    "max_value": 236,
                    "strict_min": False,
                    "column": "dropoff_location_id",
                    "min_value": 190,
                },
            }
        ),
        ExpectationConfiguration(
            **{
                "meta": {
                    "profiler_details": {
                        "metric_configuration": {
                            "metric_name": "column.distinct_values.count",
                            "domain_kwargs": {"column": "payment_type"},
                            "metric_value_kwargs": None,
                            "metric_dependencies": None,
                        },
                        "num_batches": 36,
                    }
                },
                "expectation_type": "expect_column_unique_value_count_to_be_between",
                "kwargs": {
                    "strict_max": False,
                    "max_value": 4,
                    "strict_min": False,
                    "column": "payment_type",
                    "min_value": 4,
                },
            }
        ),
        ExpectationConfiguration(
            **{
                "meta": {
                    "profiler_details": {
                        "metric_configuration": {
                            "metric_name": "column.distinct_values.count",
                            "domain_kwargs": {"column": "fare_amount"},
                            "metric_value_kwargs": None,
                            "metric_dependencies": None,
                        },
                        "num_batches": 36,
                    }
                },
                "expectation_type": "expect_column_unique_value_count_to_be_between",
                "kwargs": {
                    "strict_max": False,
                    "max_value": 899,
                    "strict_min": False,
                    "column": "fare_amount",
                    "min_value": 152,
                },
            }
        ),
        ExpectationConfiguration(
            **{
                "meta": {
                    "profiler_details": {
                        "metric_configuration": {
                            "metric_name": "column.distinct_values.count",
                            "domain_kwargs": {"column": "extra"},
                            "metric_value_kwargs": None,
                            "metric_dependencies": None,
                        },
                        "num_batches": 36,
                    }
                },
                "expectation_type": "expect_column_unique_value_count_to_be_between",
                "kwargs": {
                    "strict_max": False,
                    "max_value": 15,
                    "strict_min": False,
                    "column": "extra",
                    "min_value": 5,
                },
            }
        ),
        ExpectationConfiguration(
            **{
                "meta": {
                    "profiler_details": {
                        "metric_configuration": {
                            "metric_name": "column.distinct_values.count",
                            "domain_kwargs": {"column": "mta_tax"},
                            "metric_value_kwargs": None,
                            "metric_dependencies": None,
                        },
                        "num_batches": 36,
                    }
                },
                "expectation_type": "expect_column_unique_value_count_to_be_between",
                "kwargs": {
                    "strict_max": False,
                    "max_value": 4,
                    "strict_min": False,
                    "column": "mta_tax",
                    "min_value": 3,
                },
            }
        ),
        ExpectationConfiguration(
            **{
                "meta": {
                    "profiler_details": {
                        "metric_configuration": {
                            "metric_name": "column.distinct_values.count",
                            "domain_kwargs": {"column": "tip_amount"},
                            "metric_value_kwargs": None,
                            "metric_dependencies": None,
                        },
                        "num_batches": 36,
                    }
                },
                "expectation_type": "expect_column_unique_value_count_to_be_between",
                "kwargs": {
                    "strict_max": False,
                    "max_value": 608,
                    "strict_min": False,
                    "column": "tip_amount",
                    "min_value": 469,
                },
            }
        ),
        ExpectationConfiguration(
            **{
                "meta": {
                    "profiler_details": {
                        "metric_configuration": {
                            "metric_name": "column.distinct_values.count",
                            "domain_kwargs": {"column": "tolls_amount"},
                            "metric_value_kwargs": None,
                            "metric_dependencies": None,
                        },
                        "num_batches": 36,
                    }
                },
                "expectation_type": "expect_column_unique_value_count_to_be_between",
                "kwargs": {
                    "strict_max": False,
                    "max_value": 31,
                    "strict_min": False,
                    "column": "tolls_amount",
                    "min_value": 18,
                },
            }
        ),
        ExpectationConfiguration(
            **{
                "meta": {
                    "profiler_details": {
                        "metric_configuration": {
                            "metric_name": "column.distinct_values.count",
                            "domain_kwargs": {"column": "improvement_surcharge"},
                            "metric_value_kwargs": None,
                            "metric_dependencies": None,
                        },
                        "num_batches": 36,
                    }
                },
                "expectation_type": "expect_column_unique_value_count_to_be_between",
                "kwargs": {
                    "strict_max": False,
                    "max_value": 3,
                    "strict_min": False,
                    "column": "improvement_surcharge",
                    "min_value": 3,
                },
            }
        ),
        ExpectationConfiguration(
            **{
                "meta": {
                    "profiler_details": {
                        "metric_configuration": {
                            "metric_name": "column.distinct_values.count",
                            "domain_kwargs": {"column": "total_amount"},
                            "metric_value_kwargs": None,
                            "metric_dependencies": None,
                        },
                        "num_batches": 36,
                    }
                },
                "expectation_type": "expect_column_unique_value_count_to_be_between",
                "kwargs": {
                    "strict_max": False,
                    "max_value": 1562,
                    "strict_min": False,
                    "column": "total_amount",
                    "min_value": 896,
                },
            }
        ),
        ExpectationConfiguration(
            **{
                "meta": {
                    "profiler_details": {
                        "metric_configuration": {
                            "metric_name": "column.distinct_values.count",
                            "domain_kwargs": {"column": "congestion_surcharge"},
                            "metric_value_kwargs": None,
                            "metric_dependencies": None,
                        },
                        "num_batches": 36,
                    }
                },
                "expectation_type": "expect_column_unique_value_count_to_be_between",
                "kwargs": {
                    "strict_max": False,
                    "max_value": 4,
                    "strict_min": False,
                    "column": "congestion_surcharge",
                    "min_value": 0,
                },
            }
        ),
    ]

    expected_expectation_configurations: List[ExpectationConfiguration] = (
        [
            expected_expect_table_row_count_to_be_between_expectation_configuration,
        ]
        + expected_expect_column_unique_value_count_to_be_between_expectation_configuration_list
    )

    expectation_suite_name: str = "my_suite"

    expected_expectation_suite: ExpectationSuite = ExpectationSuite(
        expectation_suite_name=expectation_suite_name,
    )

    expectation_configuration: ExpectationConfiguration
    for expectation_configuration in expected_expectation_configurations:
        expected_expectation_suite._add_expectation(
            expectation_configuration=expectation_configuration, send_usage_event=False
        )

    expected_expectation_suite_meta: Dict[str, Any] = {
        "citations": [
            {
                "citation_date": "2019-09-26T13:42:41.000000Z",
                "profiler_config": {
                    "name": "test_volume_data_assistant",
                    "config_version": 1.0,
                    "variables": {"bootstrap_random_seed": RANDOM_SEED},
                    "rules": {
                        "default_expect_table_row_count_to_be_between_rule": {
                            "domain_builder": {
                                "module_name": "great_expectations.rule_based_profiler.domain_builder.table_domain_builder",
                                "class_name": "TableDomainBuilder",
                            },
                            "parameter_builders": [
                                {
                                    "module_name": "great_expectations.rule_based_profiler.parameter_builder.metric_multi_batch_parameter_builder",
                                    "metric_name": "table.row_count",
                                    "json_serialize": True,
                                    "class_name": "MetricMultiBatchParameterBuilder",
                                    "name": "table_row_count",
                                    "enforce_numeric_metric": True,
                                    "metric_domain_kwargs": "$domain.domain_kwargs",
                                    "evaluation_parameter_builder_configs": None,
                                    "reduce_scalar_metric": True,
                                    "replace_nan_with_zero": True,
                                    "metric_value_kwargs": None,
                                }
                            ],
                            "expectation_configuration_builders": [
                                {
                                    "module_name": "great_expectations.rule_based_profiler.expectation_configuration_builder.default_expectation_configuration_builder",
                                    "max_value": "$parameter.row_count_range_estimator.value[1]",
                                    "class_name": "DefaultExpectationConfigurationBuilder",
                                    "meta": {
                                        "profiler_details": "$parameter.row_count_range_estimator.details"
                                    },
                                    "condition": None,
                                    "validation_parameter_builder_configs": [
                                        {
                                            "module_name": "great_expectations.rule_based_profiler.parameter_builder",
                                            "json_serialize": True,
                                            "metric_name": "table.row_count",
                                            "class_name": "NumericMetricRangeMultiBatchParameterBuilder",
                                            "false_positive_rate": "$variables.false_positive_rate",
                                            "name": "row_count_range_estimator",
                                            "enforce_numeric_metric": True,
                                            "truncate_values": "$variables.truncate_values",
                                            "round_decimals": "$variables.round_decimals",
                                            "metric_domain_kwargs": None,
                                            "bootstrap_random_seed": "$variables.bootstrap_random_seed",
                                            "evaluation_parameter_builder_configs": None,
                                            "num_bootstrap_samples": "$variables.num_bootstrap_samples",
                                            "reduce_scalar_metric": True,
                                            "metric_value_kwargs": None,
                                            "estimator": "$variables.estimator",
                                            "replace_nan_with_zero": True,
                                        }
                                    ],
                                    "min_value": "$parameter.row_count_range_estimator.value[0]",
                                    "expectation_type": "expect_table_row_count_to_be_between",
                                }
                            ],
                            "variables": {
                                "false_positive_rate": 0.05,
                                "estimator": "bootstrap",
                                "num_bootstrap_samples": 9999,
                                "bootstrap_random_seed": RANDOM_SEED,
                                "truncate_values": {
                                    "lower_bound": 0,
                                    "upper_bound": None,
                                },
                                "round_decimals": 0,
                            },
                        },
                        "default_expect_column_unique_values_to_be_between_rule": {
                            "domain_builder": {
                                "exclude_column_name_suffixes": None,
                                "module_name": "great_expectations.rule_based_profiler.domain_builder.column_domain_builder",
                                "semantic_type_filter_class_name": None,
                                "class_name": "ColumnDomainBuilder",
                                "include_semantic_types": None,
                                "include_column_name_suffixes": None,
                                "exclude_column_names": None,
                                "exclude_semantic_types": None,
                                "include_column_names": None,
                                "semantic_type_filter_module_name": None,
                            },
                            "parameter_builders": [
                                {
                                    "module_name": "great_expectations.rule_based_profiler.parameter_builder.metric_multi_batch_parameter_builder",
                                    "metric_name": "column.distinct_values.count",
                                    "json_serialize": True,
                                    "class_name": "MetricMultiBatchParameterBuilder",
                                    "name": "column_distinct_values.count",
                                    "enforce_numeric_metric": True,
                                    "metric_domain_kwargs": "$domain.domain_kwargs",
                                    "evaluation_parameter_builder_configs": None,
                                    "reduce_scalar_metric": True,
                                    "replace_nan_with_zero": True,
                                    "metric_value_kwargs": None,
                                }
                            ],
                            "expectation_configuration_builders": [
                                {
                                    "column": "$domain.domain_kwargs.column",
                                    "module_name": "great_expectations.rule_based_profiler.expectation_configuration_builder.default_expectation_configuration_builder",
                                    "max_value": "$parameter.column_unique_values_range_estimator.value[1]",
                                    "class_name": "DefaultExpectationConfigurationBuilder",
                                    "strict_max": "$variables.strict_max",
                                    "meta": {
                                        "profiler_details": "$parameter.column_unique_values_range_estimator.details"
                                    },
                                    "condition": None,
                                    "validation_parameter_builder_configs": [
                                        {
                                            "module_name": "great_expectations.rule_based_profiler.parameter_builder",
                                            "json_serialize": True,
                                            "metric_name": "column.distinct_values.count",
                                            "class_name": "NumericMetricRangeMultiBatchParameterBuilder",
                                            "false_positive_rate": "$variables.false_positive_rate",
                                            "name": "column_unique_values_range_estimator",
                                            "enforce_numeric_metric": True,
                                            "truncate_values": "$variables.truncate_values",
                                            "round_decimals": "$variables.round_decimals",
                                            "metric_domain_kwargs": "$domain.domain_kwargs",
                                            "bootstrap_random_seed": "$variables.bootstrap_random_seed",
                                            "evaluation_parameter_builder_configs": None,
                                            "num_bootstrap_samples": "$variables.num_bootstrap_samples",
                                            "reduce_scalar_metric": True,
                                            "metric_value_kwargs": None,
                                            "estimator": "$variables.estimator",
                                            "replace_nan_with_zero": True,
                                        }
                                    ],
                                    "strict_min": "$variables.strict_min",
                                    "min_value": "$parameter.column_unique_values_range_estimator.value[0]",
                                    "expectation_type": "expect_column_unique_value_count_to_be_between",
                                }
                            ],
                            "variables": {
                                "mostly": 1.0,
                                "strict_min": False,
                                "strict_max": False,
                                "false_positive_rate": 0.05,
                                "estimator": "bootstrap",
                                "num_bootstrap_samples": 9999,
                                "bootstrap_random_seed": RANDOM_SEED,
                                "truncate_values": {
                                    "lower_bound": 0,
                                    "upper_bound": None,
                                },
                                "round_decimals": 0,
                            },
                        },
                    },
                },
                "comment": "Suite created by Rule-Based Profiler with the configuration included.",
            }
        ]
    }

    expected_expectation_suite.meta = expected_expectation_suite_meta

    expected_rule_based_profiler_config: RuleBasedProfilerConfig = RuleBasedProfilerConfig(
        config_version=1.0,
        name="test_volume_data_assistant",
        variables={"bootstrap_random_seed": RANDOM_SEED},
        rules={
            "default_expect_table_row_count_to_be_between_rule": {
                "variables": {
                    "false_positive_rate": 0.05,
                    "estimator": "bootstrap",
                    "num_bootstrap_samples": 9999,
                    "truncate_values": {"lower_bound": 0},
                    "round_decimals": 0,
                },
                "domain_builder": {
                    "class_name": "TableDomainBuilder",
                    "module_name": "great_expectations.rule_based_profiler.domain_builder.table_domain_builder",
                },
                "parameter_builders": [
                    {
                        "metric_domain_kwargs": "$domain.domain_kwargs",
                        "replace_nan_with_zero": True,
                        "name": "table_row_count",
                        "module_name": "great_expectations.rule_based_profiler.parameter_builder.metric_multi_batch_parameter_builder",
                        "enforce_numeric_metric": True,
                        "class_name": "MetricMultiBatchParameterBuilder",
                        "json_serialize": True,
                        "reduce_scalar_metric": True,
                        "metric_name": "table.row_count",
                    }
                ],
                "expectation_configuration_builders": [
                    {
                        "max_value": "$parameter.row_count_range_estimator.value[1]",
                        "validation_parameter_builder_configs": [
                            {
                                "replace_nan_with_zero": True,
                                "name": "row_count_range_estimator",
                                "module_name": "great_expectations.rule_based_profiler.parameter_builder",
                                "truncate_values": "$variables.truncate_values",
                                "enforce_numeric_metric": True,
                                "num_bootstrap_samples": "$variables.num_bootstrap_samples",
                                "class_name": "NumericMetricRangeMultiBatchParameterBuilder",
                                "json_serialize": True,
                                "estimator": "$variables.estimator",
                                "reduce_scalar_metric": True,
                                "metric_name": "table.row_count",
                                "false_positive_rate": "$variables.false_positive_rate",
                                "bootstrap_random_seed": "$variables.bootstrap_random_seed",
                                "round_decimals": "$variables.round_decimals",
                            }
                        ],
                        "expectation_type": "expect_table_row_count_to_be_between",
                        "module_name": "great_expectations.rule_based_profiler.expectation_configuration_builder.default_expectation_configuration_builder",
                        "meta": {
                            "profiler_details": "$parameter.row_count_range_estimator.details"
                        },
                        "class_name": "DefaultExpectationConfigurationBuilder",
                        "min_value": "$parameter.row_count_range_estimator.value[0]",
                    }
                ],
            },
            "default_expect_column_unique_values_to_be_between_rule": {
                "variables": {
                    "mostly": 1.0,
                    "strict_min": False,
                    "strict_max": False,
                    "false_positive_rate": 0.05,
                    "estimator": "bootstrap",
                    "num_bootstrap_samples": 9999,
                    "truncate_values": {"lower_bound": 0},
                    "round_decimals": 0,
                },
                "domain_builder": {
                    "module_name": "great_expectations.rule_based_profiler.domain_builder.column_domain_builder",
                    "class_name": "ColumnDomainBuilder",
                },
                "parameter_builders": [
                    {
                        "metric_domain_kwargs": "$domain.domain_kwargs",
                        "replace_nan_with_zero": True,
                        "name": "column_distinct_values.count",
                        "module_name": "great_expectations.rule_based_profiler.parameter_builder.metric_multi_batch_parameter_builder",
                        "enforce_numeric_metric": True,
                        "class_name": "MetricMultiBatchParameterBuilder",
                        "json_serialize": True,
                        "reduce_scalar_metric": True,
                        "metric_name": "column.distinct_values.count",
                    }
                ],
                "expectation_configuration_builders": [
                    {
                        "max_value": "$parameter.column_unique_values_range_estimator.value[1]",
                        "validation_parameter_builder_configs": [
                            {
                                "metric_domain_kwargs": "$domain.domain_kwargs",
                                "replace_nan_with_zero": True,
                                "name": "column_unique_values_range_estimator",
                                "module_name": "great_expectations.rule_based_profiler.parameter_builder",
                                "truncate_values": "$variables.truncate_values",
                                "enforce_numeric_metric": True,
                                "num_bootstrap_samples": "$variables.num_bootstrap_samples",
                                "class_name": "NumericMetricRangeMultiBatchParameterBuilder",
                                "json_serialize": True,
                                "estimator": "$variables.estimator",
                                "reduce_scalar_metric": True,
                                "metric_name": "column.distinct_values.count",
                                "false_positive_rate": "$variables.false_positive_rate",
                                "bootstrap_random_seed": "$variables.bootstrap_random_seed",
                                "round_decimals": "$variables.round_decimals",
                            }
                        ],
                        "expectation_type": "expect_column_unique_value_count_to_be_between",
                        "module_name": "great_expectations.rule_based_profiler.expectation_configuration_builder.default_expectation_configuration_builder",
                        "meta": {
                            "profiler_details": "$parameter.column_unique_values_range_estimator.details"
                        },
                        "class_name": "DefaultExpectationConfigurationBuilder",
                        "strict_max": "$variables.strict_max",
                        "min_value": "$parameter.column_unique_values_range_estimator.value[0]",
                        "strict_min": "$variables.strict_min",
                        "column": "$domain.domain_kwargs.column",
                    }
                ],
            },
        },
    )

    # Utilize a consistent seed to deal with probabilistic nature of this feature.
    data_assistant: DataAssistant = VolumeDataAssistant(
        name="test_volume_data_assistant",
        validator=validator,
    )
    set_bootstrap_random_seed_variable(profiler=data_assistant.profiler)
    data_assistant_result: DataAssistantResult = data_assistant.run(
        expectation_suite_name=expectation_suite_name,
    )

    assert data_assistant_result.metrics_by_domain == expected_metrics_by_domain
    assert (
        data_assistant_result.expectation_suite.expectations
        == expected_expectation_configurations
    )

    data_assistant_result.expectation_suite.meta.pop("great_expectations_version", None)

    assert data_assistant_result.expectation_suite == expected_expectation_suite

    assert (
        data_assistant_result.expectation_suite.meta == expected_expectation_suite_meta
    )

    assert deep_filter_properties_iterable(
        properties=data_assistant_result.profiler_config.to_json_dict()
    ) == deep_filter_properties_iterable(
        properties=expected_rule_based_profiler_config.to_json_dict()
    )


def test_execution_time_within_proper_bounds(
    quentin_columnar_table_multi_batch_data_context,
):
    context: DataContext = quentin_columnar_table_multi_batch_data_context

    batch_request: dict = {
        "datasource_name": "taxi_pandas",
        "data_connector_name": "monthly",
        "data_asset_name": "my_reports",
    }

    validator: Validator = get_validator_with_expectation_suite(
        batch_request=batch_request,
        data_context=context,
        expectation_suite_name=None,
        expectation_suite=None,
        component_name="volume_data_assistant",
    )
    assert len(validator.batches) == 36

    data_assistant: DataAssistant = VolumeDataAssistant(
        name="test_volume_data_assistant",
        validator=validator,
    )
    data_assistant_result: DataAssistantResult = data_assistant.run()

    # Execution time (in seconds) must have non-trivial value.
    assert data_assistant_result.execution_time > 0.0


def test_volume_data_assistant_add_expectation_configurations_to_suite_inplace_no(
    quentin_columnar_table_multi_batch_data_context,
):
    context: DataContext = quentin_columnar_table_multi_batch_data_context

    expectation_suite: ExpectationSuite = get_or_create_expectation_suite(
        data_context=context,
        expectation_suite=None,
        expectation_suite_name="my_suite",
        component_name=None,
    )
    assert len(expectation_suite.expectations) == 0

    batch_request: dict = {
        "datasource_name": "taxi_pandas",
        "data_connector_name": "monthly",
        "data_asset_name": "my_reports",
    }

    validator: Validator = get_validator_with_expectation_suite(
        batch_request=batch_request,
        data_context=context,
        expectation_suite_name=None,
        expectation_suite=expectation_suite,
        component_name="volume_data_assistant",
    )
    assert len(validator.batches) == 36

    data_assistant: DataAssistant = VolumeDataAssistant(
        name="test_volume_data_assistant",
        validator=validator,
    )
    data_assistant_result: DataAssistantResult = data_assistant.run()

    expectation_suite.add_expectation_configurations(
        expectation_configurations=data_assistant_result.expectation_suite.expectations,
        send_usage_event=False,
        match_type="domain",
        overwrite_existing=True,
    )
    assert len(expectation_suite.expectations) == 19


def test_volume_data_assistant_add_expectation_configurations_to_suite_inplace_yes_use_suite_name(
    quentin_columnar_table_multi_batch_data_context,
):
    context: DataContext = quentin_columnar_table_multi_batch_data_context

    expectation_suite_name: str = "my_suite"

    expectation_suite: ExpectationSuite

    expectation_suite = get_or_create_expectation_suite(
        data_context=context,
        expectation_suite=None,
        expectation_suite_name=expectation_suite_name,
        component_name=None,
    )
    assert len(expectation_suite.expectations) == 0

    context.save_expectation_suite(expectation_suite=expectation_suite)

    batch_request: dict = {
        "datasource_name": "taxi_pandas",
        "data_connector_name": "monthly",
        "data_asset_name": "my_reports",
    }

    validator: Validator = get_validator_with_expectation_suite(
        batch_request=batch_request,
        data_context=context,
        expectation_suite_name=expectation_suite_name,
        expectation_suite=expectation_suite,
        component_name="volume_data_assistant",
    )
    assert len(validator.batches) == 36

    data_assistant: DataAssistant = VolumeDataAssistant(
        name="test_volume_data_assistant",
        validator=validator,
    )

    data_assistant_result: DataAssistantResult

    data_assistant_result = data_assistant.run(
        expectation_suite_name=expectation_suite_name,
        save_updated_expectation_suite=False,
    )
    expectation_suite = get_or_create_expectation_suite(
        data_context=context,
        expectation_suite=None,
        expectation_suite_name=expectation_suite_name,
        component_name=None,
    )
    assert len(data_assistant_result.expectation_suite.expectations) == 19
    assert len(expectation_suite.expectations) == 0

    data_assistant_result = data_assistant.run(
        expectation_suite_name=expectation_suite_name,
        save_updated_expectation_suite=True,
    )
    expectation_suite = get_or_create_expectation_suite(
        data_context=context,
        expectation_suite=None,
        expectation_suite_name=expectation_suite_name,
        component_name=None,
    )
    assert len(data_assistant_result.expectation_suite.expectations) == 19
    assert len(expectation_suite.expectations) == 19


def test_volume_data_assistant_add_expectation_configurations_to_suite_inplace_yes_use_suite(
    quentin_columnar_table_multi_batch_data_context,
):
    context: DataContext = quentin_columnar_table_multi_batch_data_context

    expectation_suite: ExpectationSuite = get_or_create_expectation_suite(
        data_context=context,
        expectation_suite=None,
        expectation_suite_name="my_suite",
        component_name=None,
    )
    assert len(expectation_suite.expectations) == 0

    batch_request: dict = {
        "datasource_name": "taxi_pandas",
        "data_connector_name": "monthly",
        "data_asset_name": "my_reports",
    }

    validator: Validator = get_validator_with_expectation_suite(
        batch_request=batch_request,
        data_context=context,
        expectation_suite_name=None,
        expectation_suite=expectation_suite,
        component_name="volume_data_assistant",
    )
    assert len(validator.batches) == 36

    data_assistant: DataAssistant = VolumeDataAssistant(
        name="test_volume_data_assistant",
        validator=validator,
    )
    # noinspection PyUnusedLocal
    data_assistant_result: DataAssistantResult = data_assistant.run(
        expectation_suite=expectation_suite
    )
    assert len(expectation_suite.expectations) == 19


def test_volume_data_assistant_plot_descriptive_notebook_execution_fails(
    bobby_columnar_table_multi_batch_deterministic_data_context,
):
    context: DataContext = bobby_columnar_table_multi_batch_deterministic_data_context
    new_cell: str = "data_assistant_result.plot(this_is_not_a_real_parameter=True)"
    with pytest.raises(nbconvert.preprocessors.CellExecutionError):
        run_volume_data_assistant_result_jupyter_notebook_with_new_cell(
            context=context, new_cell=new_cell
        )


def test_volume_data_assistant_plot_descriptive_notebook_execution(
    bobby_columnar_table_multi_batch_deterministic_data_context,
):
    context: DataContext = bobby_columnar_table_multi_batch_deterministic_data_context
    new_cell: str = "data_assistant_result.plot()"
    run_volume_data_assistant_result_jupyter_notebook_with_new_cell(
        context=context, new_cell=new_cell
    )


def test_volume_data_assistant_plot_prescriptive_notebook_execution(
    bobby_columnar_table_multi_batch_deterministic_data_context,
):
    context: DataContext = bobby_columnar_table_multi_batch_deterministic_data_context
    new_cell: str = "data_assistant_result.plot(prescriptive=True)"
    run_volume_data_assistant_result_jupyter_notebook_with_new_cell(
        context=context, new_cell=new_cell
    )


def test_volume_data_assistant_plot_descriptive_theme_notebook_execution(
    bobby_columnar_table_multi_batch_deterministic_data_context,
):
    context: DataContext = bobby_columnar_table_multi_batch_deterministic_data_context

    theme = {"font": "Comic Sans MS"}
    new_cell: str = f"data_assistant_result.plot(theme={theme})"
    run_volume_data_assistant_result_jupyter_notebook_with_new_cell(
        context=context, new_cell=new_cell
    )


def test_volume_data_assistant_plot_prescriptive_theme_notebook_execution(
    bobby_columnar_table_multi_batch_deterministic_data_context,
):
    context: DataContext = bobby_columnar_table_multi_batch_deterministic_data_context

    theme = {"font": "Comic Sans MS"}
    new_cell: str = f"data_assistant_result.plot(prescriptive=True, theme={theme})"
    run_volume_data_assistant_result_jupyter_notebook_with_new_cell(
        context=context, new_cell=new_cell
    )
