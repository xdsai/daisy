import paramiko

host = "192.168.0.101"
user = ""
pass_ = ""

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

magnet = input("Enter magnet link: ")
ttype = input("Enter type movie/other: ")
if ttype != "movie" and ttype != "other":
    print("Invalid type")
    exit()
if ttype == "other":
    name = input("Enter name: ")
elif "subsplease" in magnet:
    name = "subsplease"
else:
    name = "mov"
remote_command = f"~/daisy_shell.sh {ttype} {name} {magnet}"

try:
    client.connect(host, username=user, password=pass_)
    stdin, stdout, stderr = client.exec_command(remote_command)
    print(stdout.read().decode())
    print(stderr.read().decode())

finally:
    client.close()