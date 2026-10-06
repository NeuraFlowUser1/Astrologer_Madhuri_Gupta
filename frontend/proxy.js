import {next,rewrite} from '@vercel/functions';
import {createRouting} from '../appointment-system/hosting/routing.mjs';
import project from '../appointment-settings/project.json' with {type:'json'};
import manifest from './dist/appointment-surface-manifest.json' with {type:'json'};
export default createRouting({project,manifest,next,rewrite});
