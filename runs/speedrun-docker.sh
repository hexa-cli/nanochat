#!/bin/bash

export OMP_NUM_THREADS=1
export NANOCHAT_BASE_DIR="${NANOCHAT_BASE_DIR:-/root/.cache/nanochat}"
mkdir -p $NANOCHAT_BASE_DIR

if [ -z "$WANDB_RUN" ]; then
    WANDB_RUN=dummy
fi

python -m nanochat.report reset

python -m nanochat.dataset -n 8
python -m nanochat.dataset -n 170 &
DATASET_DOWNLOAD_PID=$!
python -m scripts.tok_train
python -m scripts.tok_eval

echo "Waiting for dataset download to complete..."
wait $DATASET_DOWNLOAD_PID

# torchrun --standalone --nproc_per_node=1 -m scripts.base_train -- --depth=12 --target-param-data-ratio=10.5 --device-batch-size=8 --fp8 --run=$WANDB_RUN
torchrun --standalone --nproc_per_node=1 -m scripts.base_train -- --depth=10 --target-param-data-ratio=12.5 --device-batch-size=8 --run=$WANDB_RUN
torchrun --standalone --nproc_per_node=1 -m scripts.base_eval -- --device-batch-size=8

curl -L -o $NANOCHAT_BASE_DIR/identity_conversations.jsonl https://karpathy-public.s3.us-west-2.amazonaws.com/identity_conversations.jsonl

torchrun --standalone --nproc_per_node=1 -m scripts.chat_sft -- --device-batch-size=8 --run=$WANDB_RUN
torchrun --standalone --nproc_per_node=1 -m scripts.chat_eval -- -i sft

python -m nanochat.report generate
