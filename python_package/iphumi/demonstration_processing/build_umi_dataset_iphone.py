"""
Adapted from UMI codebase.
Replaces the main script for UMI SLAM pipeline to instead use the pose from iPhone.
python build_umi_dataset.py <session_dir>
"""

import os
import hydra
from omegaconf import DictConfig

from iphumi.demonstration_processing.build_umi_dataset_stages.gen_dataset_plan import gen_dataset_plan
from iphumi.demonstration_processing.utils.generic_util import (
    get_demonstration_type,
    validate_demonstration_tracking_artifacts,
)

SUPPORTED_OUTPUT_FORMATS = ('zarr',)


def _write_dataset_zarr(session_dir, session_name, dataset_plan_path, cfg, overwrite):
    from iphumi.demonstration_processing.build_umi_dataset_stages.gen_replay_buffer_zarr import gen_zarr_replay_buffer
    from iphumi.common.replay_buffer_util import print_replay_buffer_umi

    out_path = os.path.join(session_dir, f'replay_buffer_{session_name}.zarr.zip')
    if os.path.exists(out_path):
        if overwrite:
            os.remove(out_path)
        else:
            print(f'Dataset already exists at {out_path} and overwrite is not set')
            return
    gen_zarr_replay_buffer(session_dir, dataset_plan_path, out_path, cfg.replay_buffer)
    print_replay_buffer_umi(out_path)
    print(f'Dataset saved to {os.path.abspath(out_path)}')


def _write_dataset(output_format, session_dir, session_name, dataset_plan_path, cfg, overwrite):
    if output_format == 'zarr':
        _write_dataset_zarr(session_dir, session_name, dataset_plan_path, cfg, overwrite)
    else:
        raise NotImplementedError(
            f"output_format {output_format!r} is not yet supported. "
            f"Supported formats: {SUPPORTED_OUTPUT_FORMATS}"
        )


@hydra.main(config_path="config", config_name="build_umi_dataset_iphone")
def main(cfg: DictConfig):
    session_dir = cfg.session_dir
    overwrite = cfg.overwrite
    stages = cfg.stages
    output_format = str(cfg.get('output_format', 'zarr'))

    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise ValueError(
            f"Unknown output_format {output_format!r}. Supported: {SUPPORTED_OUTPUT_FORMATS}"
        )

    assert all(x in ['dataset_plan', 'replay_buffer'] for x in stages)

    session_name = os.path.basename(session_dir)
    demo_dir = os.path.join(session_dir, 'demos')
    assert os.path.isdir(demo_dir)

    dataset_plan_path = os.path.join(session_dir, 'dataset_plan.pkl')

    if 'dataset_plan' in stages:
        for demo_name in sorted(os.listdir(demo_dir)):
            demonstration_dir = os.path.join(demo_dir, demo_name)
            if get_demonstration_type(demonstration_dir) == 'demonstration':
                validate_demonstration_tracking_artifacts(demonstration_dir)

        if os.path.exists(dataset_plan_path):
            if overwrite:
                os.remove(dataset_plan_path)
            else:
                print(f'Dataset plan already exists at {dataset_plan_path} and overwrite is not set')
                exit()
        gen_dataset_plan(
            session_dir,
            dataset_plan_path,
            cfg.task_names,
        )

    if 'replay_buffer' in stages:
        _write_dataset(output_format, session_dir, session_name, dataset_plan_path, cfg, overwrite)


if __name__ == "__main__":
    main()
