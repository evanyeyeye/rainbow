#"SampleName","A2Rd2_02-1"
BEGIN { FS="," }

FNR == 1 {
    #print $0
    temp = substr($2,2,length($2)-2)
    split(temp,fields,"-")
    fields[2] -= 1

    printf "%s,\"%s-%d\"\n", $1, fields[1], fields[2]
}

FNR > 1 {
    print
}
