# Test3 - ICMP Diff Router diff subnet

```mermaid
flowchart TD
  A[client01 - 192.168.202.199 - 00:50:56:a8:5d:ad
     Default GW 192.168.202.200] -- ICMP --> R1[Router1 192.168.202.200
                                                Router1 192.168.200.200]

  R1 -- ICMP --> C1[CT0.ETH4 192.168.200.152
         Default Gateway 192.168.200.1]
  C1 --- C[CT0]
  C1 -- ICMP --> R3[Router2 192.168.200.1
            Router2 192.169.202.1]
  R3 -- ICMP --> A
  C4[CT0.ETH5 192.168.200.154] --- C[CT0]
  C2[CT0.ETH4 192.168.202.111] --- C[CT0]
  C3[CT0.ETH5 192.168.202.113] --- C[CT0]

```

# Results

This test shows that each interface has it's own unique routing table.  Even though there are interfaces directly on the target subnet 202.x for the reply, the outbound packet leaves the interface it arrived on based on it's route table. 

## How? 
[Multiple routing tables in linux](https://unix.stackexchange.com/questions/4420/reply-on-same-interface-as-incoming)