CUDA_VISIBLE_DEVICES=4,5,6,7 \
VLLM_USE_FLASHINFER_MOE_FP8=0 \
    vllm serve MiniMaxAI/MiniMax-M2.5 \
    --trust-remote-code \
    --tool-call-parser minimax_m2 \
    --enable-auto-tool-choice \
    --tensor-parallel-size 4 \
    --port 8200
