

# un nouveau fichier de config ~/.git-repo.json (comme /local/home/frq07381/.git-worktree-groups.json meme structure  (onb va le remplacer) 

# git-repo create --dir <dir>  : si pas --dir prendre le repertoire courant
 --> Affiche les repos git du repertoire avec selection multiple
--> Bouton Create / Cancel 
--> Si Create demander un nom et sauvegarde dans le fichier ~/.git-repo.json apres valiation demander si c'est le repo par default

# git-repo update --dir <dir> : si pas --dir  prendre le repertoire courant
 --> si le repertoire ne fait pas partie de la liste de repo et alors
        propose d'un créer un, donc revenir comme si git-repo create
 --> Affiche le nom du repo
 --> Affiche les repos git du repertoire avec selection multiple () cocher ceux qui sont deja présent
 --> Ok (sauvegarder celon la selection add/remove dans le fichier .json / Cancel

# git-repo remove [--dir <dir>] : supprimer un repo (groupe) du fichier ~/.git-repo.json
--> Si --dir est fourni : sélectionne le repo dont la liste contient ce répertoire (si aucun ne correspond, afficher un message et sortir)
--> Sinon : affiche la liste des noms des repos (indiquer celui qui est par défaut), sélection simple (1 à la fois)
--> Boutons Remove / Cancel
--> Remove :
      - demander une confirmation (Oui / Non) avant de supprimer
      - efface du fichier ~/.git-repo.json le repo sélectionné (seul l'entrée du fichier est supprimée, jamais les repos git sur disque)
      - si c'était le repo par défaut :
            - s'il ne reste aucun repo : plus de défaut (fichier vide/liste vide)
            - s'il ne reste qu'un repo : le prendre automatiquement comme défaut sans demander
            - s'il en reste plusieurs : afficher un menu (sélection simple) pour choisir le nouveau repo par défaut
      - sauvegarder le fichier puis afficher un message de confirmation
--> Cancel : sortir sans rien modifier


change menu, quand on fait git-repo çà affiche la lister de repos (on peut les selection) bouton Go / Select / Quit . Si Go : faire directement un cd vers le répertoire du repo sélectionné et sortir (comme le bouton Go du menu du repo). La création d'un repo se fait avec git-repo create (ou automatiquement si aucun repo n'est défini).

# git repo : Affiche Affiche la liste des noms des repos (indiquer celui est par default) on peut les selectionnes (1 à la fois)
 --> Boutoon List / Update / Remove (plus de choix Go dans ce menu)
        List affiche la liste des repos git (selection simple), boutons Go / Back
              Go : faire un cd du repertoire du repo git selectionne et sortir, effacer proprement l'ecran, printer le directory en path complet
              Back : retour au menu du repo
        Update commoe git-repo update
        Remove comme git-rep remove
        bouton quit

