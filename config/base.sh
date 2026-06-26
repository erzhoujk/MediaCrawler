  uv run python scripts/xhs_creator_commenter_flow.py \
    --creator 'https://www.xiaohongshu.com/user/profile/611e5ad60000000001002eca?xsec_token=ABlRHloXrfyvuWDbji9ZMiyfr-z9rbyKintXCzqIr0ID8=&xsec_source=pc_note' \
    --max-creator-notes 15 \
    --max-comments-per-note 10 \
    --max-commenter-notes 3 \
    --max-commenters 100 \
    --headless true