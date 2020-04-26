import itertools
import gpuscheduler
import argparse
import os
import uuid
import hashlib
from itertools import product

parser = argparse.ArgumentParser(description='Compute script.')
parser.add_argument('--dry', action='store_true')
parser.add_argument('--verbose', action='store_true')
args = parser.parse_args()

cmd = 'OMP_NUM_THREADS=1 fairseq-train --task language_modeling --share-decoder-input-output-embed   --sample-break-mode none --ddp-backend=no_c10d --log-format simple --log-interval 50 --fp16 --keep-best-checkpoints 1 --no-epoch-checkpoints'

args2 = {}
#args2['warmup-updates'] = 400
args2['optimizer'] = 'adam'
args2['adam-betas'] = "'(0.9, 0.98)'"

#args2['max-tokens'] = 1024
#args2['update-freq'] = 2
args2['max-tokens'] = 2048
args2['update-freq'] = 1

args2['clip-norm'] = 0.0003
args2['weight-decay'] = 1e-07
args2['dropout'] = 0.35
args2['attention-dropout'] = 0.2
args2['activation-dropout'] = 0.0
# seq length
#args2['tokens-per-sample'] = 128
args2['lr-scheduler'] = 'inverse_sqrt'

#args2['lr-period-updates'] = 270000
#args2['max-lr'] = 1.0
#args2['max-update'] = 25000
args2['min-lr'] = 1e-09
args2['warmup-init-lr'] = 1e-07
args2['lr'] = 0.0007
#args2['decoder-embed-dim'] = 400
#args2['decoder-ffn-embed-dim'] = 2048
#args2['decoder-layers'] = 16
args2['write-loss-folder'] = './clean_losses'
args2['arch'] = 'transformer_lm'
args2['decoder-attention-heads'] = 16
#args2['adaptive-input-cutoff'] = '20000,60000'
#args2['adaptive-softmax-cutoff'] '20000,60000'
#args2['share-decoder-input-output-embed'] = ''
#args2['criterion'] = 'adaptive_loss'
#args2['decoder-input-dim'] = 1200
#args2['decoder-output-dim'] = 1200


logfolder = 'interpolation/{0}/'.format('test1')
#time_hours = 24*2
time_hours = 72
cores_per_job = 4
mem = 24
num_seeds = 1
seed_offset = 0
constraint = 'volta16gb'
ckp_name = 'small_datasets'

#account = 'cse'
#account = 'stf'
#account = 'ark'
#partition = 'scavenge'
#partition = 'scavenge,learnfair'
partition = 'learnfair'
#partition = 'uninterrupted'
#partition = 'dev'
change_dir = 'fairseq_private/'
repo = 'fairseq_private'

s = gpuscheduler.HyakScheduler(verbose=args.verbose, account='', partition=partition, use_gres=False)
#s = gpuscheduler.SshScheduler(verbose=args.verbose)

for key, value in args2.items():
    cmd = cmd + ' --{0} {1}'.format(key, value)

fp16 = True
args3 = {}
#args3['max-update'] = [15000, 25000, 35000, 50000]
args3['dropout'] = [0.1, 0.3]
#args3['attention-dropout'] = [0.0, 0.20]
args3['decoder-embed-dim'] = [256, 512]
args3['decoder-ffn-embed-dim'] = [1024, 2048]
args3['decoder-layers'] = [4, 8]
args3['tokens-per-sample'] = [128, 192]
args4 = []
# about 15 minutes for WT1
#for wt in [1]:
#for wt in [1,2,3,4,5]:
#for wt in [7, 10, 15]:
#for wt in [25]:
#for wt in [50]:
#for wt in [75]:
for wt in [103]:
    args4.append(' --max-update {0} --warmup-updates {1} data/wikitext-{2} '.format(int(35000/2.0*wt), int(400/2.0*wt), wt))


args_prod = []
for key, values in args3.items():
    if len(key) == 0:
        keyvalues = [' --{0}'.format(v) if len(v) > 0 else '{0}'.format(v) for v in values]
    else:
        keyvalues = [' --{0} {1}'.format(key, v) for v in values]
    args_prod.append(keyvalues)

if len(args_prod) >= 2:
    args_prod = list(product(*args_prod))
else:
    new_args = []
    if len(args_prod) > 0:
        for arg in args_prod[0]:
            new_args.append([arg])
        args_prod = new_args

jobs = []
if len(args4) == 0: args4.append('')
for seed in range(num_seeds):
    seed = seed + seed_offset
    for arg4 in args4:
        if len(args_prod) == 0: args_prod.append(('', ''))
        for i, values in enumerate(args_prod):
            job_cmd = cmd + ' --seed {0} '.format(seed) + arg4
            for val in values:
                job_cmd += ' {0}' .format(val)
            save_path = ' --save-dir /checkpoint/timdettmers/{1}/{0} '.format(hashlib.md5(str(job_cmd).encode('utf-8')).hexdigest(), ckp_name)
            job_cmd = job_cmd + save_path
            if not fp16: job_cmd = job_cmd.replace('--fp16', '')
            jobs.append(job_cmd)
            s.add_job(logfolder, repo, change_dir, job_cmd, time_hours, fp16, cores=cores_per_job, mem=mem, constraint=constraint)

if args.dry:
    for job in jobs:
        print(job)
    print('total jobs', len(jobs))
    print('Jobs will be written to: {0}'.format(logfolder))
    print('Jobs will be run on: {0}'.format(partition))

if not args.dry:
    s.run_jobs()

