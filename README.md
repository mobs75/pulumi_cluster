# Esempio di Workflow Completo

# Se hai già il tuo script Pulumi pronto, il workflow tipico sarà:

# 1. Assicurati di essere loggato
    
pulumi login --local

# 2. Controlla cosa succederà prima di applicare le modifiche
    
pulumi preview

 # 3. Crea l'infrastruttura
    
pulumi up

# 4. Controlla le risorse create
    
pulumi stack output
pulumi state list

# 5. Se vuoi distruggere tutto
     
pulumi destroy
