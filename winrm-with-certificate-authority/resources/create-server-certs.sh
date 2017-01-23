#!/bin/bash

SCRIPTNAME=$(basename $0)
SCRIPTDIR=$(cd -P $(dirname $0) && pwd)
EXIT_SUCCESS=0
EXIT_FAILURE=1
EXIT_ERROR=2
EXIT_FATAL=10

function usage {
  echo "Usage: $SCRIPTNAME [-h] [-c openssl.cnf] -r root.crt -k root.key [-d outdir] [-u ATTR=value] [serverlist ...]" >&2
  [[ $# -eq 1 ]] && exit $1 || exit $EXIT_FAILURE
}

function join { local IFS="$1"; shift; echo "$*"; }

function getPasswordFromUser
{
	local RETRY=3
    while [ -z "$PASSWORD" ] && [ 0 -lt $RETRY ]
    do
		((RETRY-=1))
        read -se -p "$1: " PASSWORD1
		echo >&2
        if [ "$2" = "true" ]; then
			read -se -p "Verifying – $1: " PASSWORD2
			echo >&2
		fi

        if [ "$2" = "false" ] || [ "$PASSWORD1" = "$PASSWORD2" ]; then
            PASSWORD=$PASSWORD1
        else
            # Output error message in red
            red='\033[0;31m'
            NC='\033[0m' # No Color
            echo -e "${red}Passwords did not match!${NC}" >&2
        fi
    done
    echo "$PASSWORD"
}

# DEFAULTS
#DATE="$(date '+%d.%m.%Y %H:%M:%S')"
#PUBLISH_DATE="$DATE"
EXTBLOCK='server_exts'

while getopts ':c:r:k:d:v:h:u:e:' OPTION; do
	case $OPTION in
		h) usage $EXIT_SUCCESS
		   ;;
		v) VERBOSE=n
		   ;;
		c) SSLCONF="$OPTARG"
		   ;;
		r) ROOTCERT="$OPTARG"
		   ;;
		k) ROOTKEY="$OPTARG"
		   ;;
		e) EXTBLOCK="$OPTARG"
		   ;;
		d) OUTDIR="$OPTARG"
		   ;;
		u) SUBJ[${#SUBJ[*]}]="$OPTARG"
		   ;;
		\?) echo "Unknown option \"-$OPTARG\"." >&2
			usage $EXIT_ERROR
			;;
		:) echo "Option \"-$OPTARG\" needs an argument." >&2
		   usage $EXIT_ERROR
		   ;;
		*) echo "This shouldn't happen ..." >&2
		   usage $EXIT_FATAL
		   ;;
	esac
done

shift $(( OPTIND -1 ))

# Test for mandatory options
red='\033[0;31m' # Red text
NC='\033[0m' # No Color

if [[ -z $SSLCONF ]]; then echo -e "Warning: No openssl.cnf specified. \
This script will not work with the default config, so as long as you \
haven't adjusted yours, please provide a filename!" >&2
fi
if [[ -z $ROOTCERT ]]; then
	echo -e "${red}Error: No root certificate specified.${NC}" >&2
	ERRORS=t
elif ! [[ -r $ROOTCERT ]]; then
	echo -e "${red}Error: Root certificate does not exist or is not \
readable.${NC}" >&2
	ERRORS=t
fi
if [[ -z $ROOTKEY ]]; then
	echo -e "${red}Error: No private key for the root certificate \
specified.${NC}" >&2
	ERRORS=t
elif ! [[ -r $ROOTKEY ]]; then
	echo -e "${red}Error: Private key does not exist or is not readable.\
${NC}" >&2
	ERRORS=t
fi
if [[ -z $OUTDIR ]]; then
	echo "Warning: No output directory specified. Server certificates \
will be created in the current working directory." >&2
elif ! [[ -d $OUTDIR ]] || ! [[ -w $OUTDIR ]]; then
	echo -e "${red}Error: Output directory does not exist or is not \
writable.${NC}" >&2
	ERRORS=t
fi
if [[ -d $OUTDIR ]] && [[ $OUTDIR != */ ]]; then
	OUTDIR="$OUTDIR/"
fi
if [[ -z $SUBJ ]]; then
	echo "Warning: Missing subject information. Certificates will be \
created with default values for country, state, location, organisation \
and organisational unit that might not reflect reality." >&2
fi
if [[ $ERRORS == t ]]; then
	usage $EXIT_ERROR;
fi

for i in ${!SUBJ[*]}
do
  SUBJ[$i]="${SUBJ[$i]}"
done

SUBJSTR=$(printf '/%s' "${SUBJ[@]}")
export ROOT_PASSWD=$(getPasswordFromUser "Enter pass phrase for \
root.key" false)
export EXPORT_PASSWD=$(getPasswordFromUser "Enter export password for \
server certificates" true)

#set -e
#set -x
PIPE=$(mktemp -u)
mkfifo $PIPE

cat <(
if [ -t 0 ]; then
    for ARG
	do
		if [[ ! -r $ARG ]]; then echo "Error: File \"$ARG\" does not \
exist or is not readable." >&2; ERRORS=t; fi
		cat $ARG
	done
	if [[ ERRORS == t ]]; then usage $EXIT_ERROR; fi
else
    cat "$@"
fi
) | while read SERVER;
do
	export FQDN="$SERVER"
	export HOSTNAME=$(cut -d. -f1 <<<"$SERVER")
	export SAN="DNS:$HOSTNAME,DNS:$FQDN"
	openssl req -batch -new -newkey rsa:4096 -nodes -keyout $PIPE \
			-sha256 -config ./openssl-ap.cnf -extensions "$EXTBLOCK" \
			-subj "$SUBJSTR/CN=$FQDN" 2>/dev/null \
		| openssl x509 -req -CA root.crt -CAkey root.key \
				  -CAcreateserial -days 365 -sha256 \
				  -extfile ./openssl-ap.cnf -extensions "$EXTBLOCK" \
				  -passin env:ROOT_PASSWD 2>/dev/null \
		| openssl pkcs12 -export -out "$OUTDIR$SERVER.pfx" \
				  -passout env:EXPORT_PASSWD -clcerts -inkey $PIPE \
				  2>/dev/null
	echo "certificate saved as $OUTDIR$SERVER.pfx"
done

rm $PIPE
echo "all done" >&2
