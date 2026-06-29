import hydra
from omegaconf import DictConfig
from iphumi.demonstration_processing.utils.color_util import blue
from iphumi.demonstration_processing.utils.generic_util import iterate_demonstrations
from iphumi.demonstration_processing.process_stages.group import group_iphone_data
from iphumi.demonstration_processing.process_stages.validate import validate_iphone_data
from iphumi.demonstration_processing.process_stages.align_validate import align_validate_iphone_data
from iphumi.demonstration_processing.process_stages.detect import detect_ar_tag_iphone
from iphumi.demonstration_processing.process_stages.calibrate import calibrate_gripper_range_iphone
from iphumi.demonstration_processing.process_stages.align import align_multi_iphone_data
from iphumi.demonstration_processing.process_stages.visualize import visualize_iphone_data
from iphumi.demonstration_processing.process_stages.label import auto_label

@hydra.main(version_base="1.2", config_name="process_demos_iphone", config_path="./config")
def main(cfg: DictConfig):
    # Determine which stages to run
    all_stages = ['group', 'group_validate', 'detect', 'calibrate', 'label', 'align', 'align_validate', 'visualize']

    if cfg.stages is None:
        cfg.stages = all_stages

    stages = [stage for stage in cfg.stages if stage not in cfg.skip_stages]
    assert all([stage in all_stages for stage in stages])

    # Define demonstration iterator
    get_demonstration_iterator = lambda demo_type=None: iterate_demonstrations(cfg.demonstrations_dir, cfg.filters, demo_type)

    # Run requested stages
    if 'group' in stages:
        print(blue("--- GROUPING STAGE ---"))
        group_iphone_data(cfg.group)

    if 'group_validate' in stages:
        print(blue("\n--- GROUP VALIDATE STAGE ---"))
        validate_demo_iterator = lambda: iterate_demonstrations(cfg.demonstrations_dir, cfg.filters)
        validate_iphone_data(validate_demo_iterator, cfg.group_validate)

    if 'detect' in stages:
        print(blue("\n--- DETECT AR TAG STAGE ---"))
        detect_ar_tag_iphone(get_demonstration_iterator, cfg.detect)

    if 'calibrate' in stages:
        print(blue("\n--- CALIBRATE GRIPPER STAGE ---"))
        calibrate_gripper_range_iphone(get_demonstration_iterator, cfg.calibrate)

    if 'align' in stages:
        print(blue("\n--- ALIGN STAGE ---"))
        align_multi_iphone_data(get_demonstration_iterator, cfg.align)

    if 'align_validate' in stages:
        print(blue("\n--- ALIGN VALIDATE STAGE ---"))
        align_validate_iphone_data(get_demonstration_iterator, cfg.align_validate)

    if 'label' in stages:
        print(blue("\n--- LABEL STAGE ---"))
        auto_label(get_demonstration_iterator, cfg.label)

    if 'visualize' in stages:
        print(blue("\n--- VISUALIZE STAGE ---"))
        visualize_iphone_data(get_demonstration_iterator, cfg.visualize)

if __name__ == '__main__':
    main()
