# Third-Party Notices

This file records important third-party components associated with the Kinova Gen3 integration. It is not a substitute for the license terms distributed with each dependency.

## Hugging Face LeRobot

This repository is derived from [Hugging Face LeRobot](https://github.com/huggingface/lerobot).

- Upstream license: Apache License 2.0
- Local license file: [LICENSE](LICENSE)

Changes made in this repository do not alter the license terms of third-party components.

## Kinova Kortex API

The repository currently contains:

`kinova/kortex_api-2.5.0.post6-py3-none-any.whl`

The Kinova optional dependency in `pyproject.toml` installs this local wheel together with the compatible protobuf version.

For purposes of this project, the bundled wheel is treated as BSD-3-Clause licensed, consistent with the license published in Kinova's official Kortex API repository.

- Copyright notice: Copyright (c) 2018, Kinova inc.
- License: BSD 3-Clause "Revised" License
- Official project: [Kinova Kortex API](https://github.com/Kinovarobotics/Kinova-kortex2_Gen3_G3L)
- Reproduced license notice: [THIRD_PARTY_LICENSES/KINOVA_KORTEX_BSD-3-CLAUSE.txt](THIRD_PARTY_LICENSES/KINOVA_KORTEX_BSD-3-CLAUSE.txt)

The wheel remains third-party software and is not relicensed under this repository's Apache-2.0 license. Binary redistributions must retain the Kinova copyright notice, BSD conditions, and disclaimer in the documentation or other materials supplied with the distribution.

Kinova, Kortex, and related product names may be trademarks of their respective owners. Their use here identifies compatibility and does not imply endorsement.

## Python dependencies

Other Python packages are resolved through the project's dependency configuration and remain subject to their own licenses. Kinova-related installations may include, among others:

- `protobuf`
- `feetech-servo-sdk`
- OpenCV
- FFmpeg/PyAV-related components

Consult the installed package metadata and upstream projects for their current license terms.

## Media, models, and datasets

Upstream documentation may link to externally hosted media, models, and datasets. Those artifacts can have terms different from the source-code license. Review the applicable model cards, dataset cards, and hosting terms before redistribution or commercial use.
