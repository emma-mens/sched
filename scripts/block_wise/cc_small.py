import numpy as np
import itertools
import gpuscheduler
import argparse
import os
import uuid
import hashlib
import glob
import math
from itertools import product
from torch.optim.lr_scheduler import OneCycleLR
from itertools import product

from os.path import join

parser = argparse.ArgumentParser(description='Compute script.')
parser.add_argument('--dry', action='store_true')
parser.add_argument('--verbose', action='store_true')
parser.add_argument('--p', type=float, default=1.0, help='Probability with which to select a configuration.')
args = parser.parse_args()


gpus = 8
cmd = 'MKL_THREADING_LAYER=GNU OMP_NUM_THREADS=1 fairseq-train --task language_modeling --share-decoder-input-output-embed --sample-break-mode none --ddp-backend=no_c10d --log-format simple --log-interval 50 --fp16 --keep-best-checkpoints 1 --no-epoch-checkpoints --keep-interval-updates 1 --distributed-port 12597 --distributed-world-size {0} --valid-subset valid'.format(gpus)

args2 = {}

name = 'ablations3'
constraint = 'volta'

logfolder = 'block_wise/cc_small/{0}'.format(name)
ckp_name = logfolder
cores_per_job = 4
mem = 24*(8 if gpus > 8 else gpus)
num_seeds = 1
seed_offset = 3
time_hours = 6
time_minutes = 0

#partition = 'learnlab,learnfair,scavenge'
partition = 'prioritylab,learnlab,learnfair'

begin = None
#begin = 'now+8hours'
#begin = 'now+16hours'
#begin = '19:00'
#begin = '03:00'
#partition = 'scavenge'

change_dir = 'fairseq_private/'
repo = 'fairseq_private'
exclude = ''

s = gpuscheduler.HyakScheduler(verbose=args.verbose, account='', partition=partition, use_gres=False)

fp16 = True
args3 = {}

key = ('decoder-embed-dim', 'decoder-ffn-embed-dim', 'decoder-attention-heads', 'decoder-input-dim', 'decoder-output-dim')
args3[key] = []
for model_dim in [1024]:
    heads = 8*(model_dim//512)
    for ff_dim in [8192]:
        args3[key].append((model_dim, ff_dim, heads, model_dim, model_dim))

args2['arch'] = 'transformer_lm'
args2['weight-decay'] = 0.00
args2['validate-interval-updates'] = 1000
args2['save-interval-updates'] = 1000
args2['lr-scheduler'] = 'cosine'
args2['optimizer'] = 'adam'
args2['fp16-no-flatten-grads'] = ''
args2['min-loss-scale'] = 1e-10
args2['fp16-scale-window'] = 250
#args2['clip-norm'] = 0.6

#args2['use-bnb'] = ''
#args2['optim-bits'] = 32

#args3[('optim-bits', 'use-bnb', 'no-scale-embedding', 'stable-emb')] = [(8, True, True, True), (32, False, False, False)]
#args3[('optim-bits', 'use-bnb', 'no-scale-embedding', 'stable-emb')] = [(8, True, True, True)]#, (32, False, False, False)]
args3[('optim-bits', 'use-bnb', 'no-scale-embedding', 'stable-emb')] = [(32, False, False, False)]
args3[('clip-norm', 'percentile-clipping')] = [(0.6, 100)]

adam1 = [0.8, 0.85, 0.9]
adam2 = [0.98, 0.99, 0.999]
adam_values = list(product(adam1, adam2))
print(adam_values)

#args3['adam-betas'] = [f"'({v1}, {v2})'" for v1, v2 in adam_values] # baseline params
args3['adam-eps'] = [1e-5, 1e-6, 1e-7, 1e-8, 1e-9]

args3['adam-betas'] = ["'(0.9, 0.995)'"] # baseline params
#args3['adam-eps'] = [1e-7] # baseline params

args3['decoder-layers'] = [10]
args3[('max-tokens', 'update-freq', 'tokens-per-sample')] = []
args3[('max-tokens', 'update-freq', 'tokens-per-sample')].append((2048, 128//gpus, 512))
args3[('dropout', 'attention-dropout', 'relu-dropout')] = [(0.0, 0.0, 0.0)]

args3[('max-update', 'warmup-updates', '')] = [(16000, 3000, ' /private/home/timdettmers/data/cc_small')]

args3['weight-decay'] = [0.00]

key = ('lr', 'warmup-init-lr')
args3[key] = []
#for params in [1e1, 1e2, 1e3, 1e4, 1e5, 1e6, 1e7]:
for params in [1e5]:
    lr = 0.003239 + (-0.0001395*math.log(params))
    #args3[key].append((lr, lr*0.1))
    args3[key].append((lr, 0.0))
args4 = []

args5 = {}

args6 = {}

rdm = np.random.RandomState(5345)

for key, value in args2.items():
    if value == True:
        cmd = cmd + ' --{0}'.format(key)
    else:
        cmd = cmd + ' --{0} {1}'.format(key, value)

args_prod = []
for key, values in args3.items():
    if isinstance(key, tuple):
        keyvalues = []
        for tups in values:
            arg = ''
            for i, v in enumerate(tups):
                if v is True: v = ''
                if v is False: continue
                if len(key[i]) == 0:
                    arg += '{0} '.format(v)
                else:
                    arg += '--{0} {1} '.format(key[i], v)
            keyvalues.append(arg)
    elif isinstance(key, str):
        keyvalues = []
        for v in values:
            if v is True: v = ''
            if v is False:
                keyvalues.append('')
            else:
                keyvalues.append(' --{0} {1}'.format(key, v))
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
            job_cmd = cmd + arg4
            for val in values:
                job_cmd += ' {0}' .format(val)
            #job_cmd += ' --checkpoint /checkpoint/timdettmers/{1}/{0}/model.pt'.format(hashlib.md5(str(job_cmd).encode('utf-8')).hexdigest(), ckp_name)
            if not fp16: job_cmd = job_cmd.replace('--fp16 ', ' ')
            if any([k in job_cmd for k in args5.keys()]):
                for substr, pdict in args5.items():
                    if substr in job_cmd:
                        for key, values in pdict.items():
                            for v in values:
                                job_cmd5 = job_cmd + ' --{0} {1}'.format(key, v)
                                job_cmd5 = job_cmd5 + ' --seed {0}'.format(seed)
                                checkpoint_dir = '/checkpoint/timdettmers/{1}/{0} '.format(hashlib.md5(str(job_cmd5).encode('utf-8')).hexdigest(), ckp_name)
                                save_dir = ' --save-dir {0}'.format(checkpoint_dir)
                                job_cmd5 = job_cmd5 + save_dir
                                cmds = [job_cmd5]
                                if rdm.rand(1) <= args.p:
                                    jobs.append(job_cmd5)
                                    s.add_job(logfolder, repo, change_dir, cmds, time_hours, fp16, cores=cores_per_job, mem=mem, constraint=constraint, exclude=exclude, time_minutes=time_minutes, gpus=gpus)
            else:
                job_cmd = job_cmd + ' --seed {0}'.format(seed)
                checkpoint_dir = '/checkpoint/timdettmers/{1}/{0} '.format(hashlib.md5(str(job_cmd).encode('utf-8')).hexdigest(), ckp_name)
                save_dir = ' --save-dir {0}'.format(checkpoint_dir)
                job_cmd = job_cmd + save_dir
                cmds = [job_cmd]
                if rdm.rand(1) <= args.p:
                    jobs.append(job_cmd)
                    s.add_job(logfolder, repo, change_dir, cmds, time_hours, fp16, cores=cores_per_job, mem=mem, constraint=constraint, exclude=exclude, time_minutes=time_minutes, gpus=gpus)

if args.dry:
    for i, job in enumerate(jobs):
        print(i, job)
    print('')
    print('Total jobs', len(jobs))
    print('Time hours: {0}'.format(time_hours))
    print('GPUs: {0}'.format(gpus))
    print('begin: {0}'.format(begin))
    print('Jobs will be written to: {0}'.format(join('/private/home/timdettmers/logs/', logfolder)))
    print('Jobs will be run on: {0}'.format(partition))
    print('Run in folder: {0}'.format(change_dir))

if not args.dry:
    s.run_jobs(begin=begin, comment='"ICLR internal review deadline 2021-09-21"')

