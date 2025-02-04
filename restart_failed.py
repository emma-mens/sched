import os
import argparse
import subprocess
import shlex
import datetime

parser = argparse.ArgumentParser('Script to restart failed or timeouted jobs.')
parser.add_argument('--startid', type=int, required=True, help='Restart all failed or timeouted jobs with this jobid or greater.')
parser.add_argument('--endid', type=int, default=None, help='Restart all failed or timeouted jobs with this jobid or smaller.')
parser.add_argument('--dry', action='store_true', help='Dry run the scripts to execute')
parser.add_argument('--no-exclude', action='store_true', help='Does not exclude any nodes from being run on.')
parser.add_argument('--include-failed', action='store_true', help='Includes failed jobs.')
parser.add_argument('--state', type=str, default='' ,help='If set only restarts jobs with a specific status: {FAILED,PREEMPTED,TIMEOUT}.')
parser.add_argument('--days-back', type=int, default=1 ,help='How long in the history to look for failed jobs.')
parser.add_argument('--restart-cancelled', action='store_true', help='Restarts cancelled jobs.')
parser.add_argument('--verbose', action='store_true', help='Prints commands with script names')

args = parser.parse_args()

def execute_and_return(strCMD):
    proc = subprocess.Popen(strCMD, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    out, err = proc.communicate()
    out, err = out.decode("UTF-8").strip(), err.decode("UTF-8").strip()
    return out, err


cmd = 'sacct -X --format="Jobid%30,State%20,JobName%250,NodeList" --noheader -S {0} -p'.format(datetime.date.today()-datetime.timedelta(days=args.days_back))

out, err = execute_and_return(cmd)

if len(err) > 0:
    print(err)
    exit()

lines = out.split('\n')

if args.restart_cancelled and args.include_failed:
    states = set(['FAILED', 'TIMEOUT', 'PREEMPTED', 'CANCELLED'])
elif args.restart_cancelled:
    states = set(['TIMEOUT', 'PREEMPTED', 'CANCELLED'])
elif args.include_failed:
    states = set(['FAILED', 'TIMEOUT', 'PREEMPTED'])
else:
    states = set(['TIMEOUT', 'PREEMPTED'])

banned = set()
restarts = set()
script2data = {}
for l in lines:
    data = [col for col in l.split('|') if len(col) > 0]
    jobstr = data[0]
    state = data[1]
    script = data[2]
    node = data[3]
    array_id = 0
    if 'CANCELLED' in state: state = 'CANCELLED'

    if '[' in jobstr:
        # array main job
        continue

    if '_' in jobstr:
        jobid = int(jobstr[:jobstr.index('_')])
        array_id = int(jobstr[jobstr.index('_')+1:])
    else:
        jobid = int(jobstr)

    script_id = script + '_{0}'.format(array_id)

    if 'array' in script:
        if not os.path.exists(script): continue
        with open(script) as f:
            lines = f.readlines()
        if array_id >= len(lines): continue
        script_name = lines[array_id].strip()
    else:
        script_name = script

    if script_name in script2data and state in ['RUNNING', 'COMPLETED', 'PENDING']:
        # job already restarted successfully, no action needed, remove job
        print('Script {1} has already been restarted and is {2} as {0}'.format(jobid, script_id, state))
        #restarts.discard(script_name)
        #script2data.pop(script_name)
    if state not in states: continue
    # add nodes that failed in the past even though the job to restart might not have failed on it
    if state == 'FAILED' and not args.no_exclude: banned.add(node)
    if jobid < args.startid: continue
    if args.endid is not None and jobid > args.endid: continue
    if args.state != '' and state != args.state: continue
    script2data[script_name] = (script, array_id, jobstr, state, node)
    restarts.add(script_name)

print('Banned nodes: {0}'.format(','.join(banned)))
if args.dry:
    print('')
    print('='*80)
    print('Restarting the following {0} jobs...'.format(len(restarts)))
    print('='*80)
    print('')
for script_name in restarts:
    if not args.dry:
        data = script2data[script_name]
        print('Originally: Job {0} with State {1} on NodeList {2}'.format(*data[-3:]))
        script, array_id, jobstr, state, node = data
        if 'array_jobs' in script:
            print('Restarting script: {0}'.format(script_name))
            cmd = 'sbatch --exclude={1} {0}'.format(script_name, ','.join(banned))
        else:
            print('Restarting script: {0}'.format(script_name))
            cmd = 'sbatch --exclude={1} {0}'.format(script_name, ','.join(banned))

        out, err = execute_and_return(cmd)
        if len(err) > 0:
            print('Error in sbatch call: {0}'.format(err))
    else:
        data = script2data[script_name]
        print('Originally: Job {0} with State {1} on NodeList {2}'.format(*data[-3:]))
        if args.verbose:
            script, array_id, jobstr, state, node = data
            if 'array_jobs' in script:
                cmd = 'sbatch --exclude={1} {0}'.format(script_name, ','.join(banned))
            if args.verbose:
                print(cmd)

